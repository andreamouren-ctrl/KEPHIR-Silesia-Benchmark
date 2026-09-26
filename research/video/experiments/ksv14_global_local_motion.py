#!/usr/bin/env python3
"""
KSV-14 Global Translation + Local Motion.

Research hypothesis:
AURORA's natural-video weakness is not simply the local radius, but the absence
of a cheap wide-field motion model for coherent camera/scene translation.

Per inter frame:
1. estimate one global even-pixel translation over a wide sparse luma field;
2. run the existing 25-candidate local ±4 search around that global vector;
3. reserve one motion-map code for absolute zero-motion fallback at borders;
4. serialize global vector + local map + residuals;
5. compare final KHEPRI bytes, not frontend bytes.

Policies emitted:
- baseline: TEMP / MC8R4 MOD8 / MC8R4 ZZ_INTER;
- global_local: TEMP / GL MOD8 / GL ZZ_INTER;
- oracle: best of all baseline + global-local candidates.

All emitted streams are independently decoded and SHA verified.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import tempfile
import time
import zlib
from collections import Counter
from pathlib import Path

import numpy as np

import ksv13_natural_radius_sweep as k13
from kstream_video_motion_control import (
    candidates as local_candidates,
    frame_sizes,
    split_frame,
    spatial_frame,
    spatial_frame_inv,
    decode_file as mc_decode,
)
from kstream_video_residual_symbols_v7 import (
    ZZ_INTER,
    map_residual,
    unmap_residual,
    decode_file as zz_decode,
)

OUT = Path("results/video/ksv14_global_local")

BLOCK = 8
LOCAL_RADIUS = 4
GLOBAL_RADIUS = 24
GLOBAL_COARSE_STEP = 4
GLOBAL_FINE_STEP = 2
GLOBAL_SAMPLE_STEP = 8
ZERO_FALLBACK_INDEX = 25

FMT_YUV420P8 = 1
GL_MAGIC = b"K14G"
GL_VERSION = 1
GL_MOD8 = 0
GL_ZZ = 1
GL_HDR = struct.Struct("<4sBBBBBBBHHII")
GL_CHUNK = struct.Struct("<III")
GL_VEC = struct.Struct("<bb")

OUTER_MAGIC = b"K14O"
OUTER_VERSION = 1
OUTER_HDR = struct.Struct("<4sBHHIIII")
OUTER_ENT = struct.Struct("<BII")

MODE_TEMP = 0
MODE_R4_MOD8 = 1
MODE_R4_ZZ = 2
MODE_GL_MOD8 = 3
MODE_GL_ZZ = 4


def split_np(frame: bytes, w: int, h: int):
    y, u, v, cw, ch = split_frame(frame, w, h)
    return (
        np.frombuffer(y, dtype=np.uint8).reshape(h, w),
        np.frombuffer(u, dtype=np.uint8).reshape(ch, cw),
        np.frombuffer(v, dtype=np.uint8).reshape(ch, cw),
    )


def _ordered_global_candidates(radius: int, step: int):
    values = range(-radius, radius + 1, step)
    pts = [(dx, dy) for dy in values for dx in values]
    pts.sort(
        key=lambda p: (
            abs(p[0]) + abs(p[1]),
            abs(p[1]),
            abs(p[0]),
            p[1],
            p[0],
        )
    )
    return pts


def estimate_global_translation(
    frame: bytes,
    prev: bytes,
    w: int,
    h: int,
    global_radius: int = GLOBAL_RADIUS,
):
    cy, _, _ = split_np(frame, w, h)
    py, _, _ = split_np(prev, w, h)

    margin = global_radius + LOCAL_RADIUS
    if w <= 2 * margin or h <= 2 * margin:
        raise ValueError("frame too small for global-motion estimator")

    ys = np.arange(margin, h - margin, GLOBAL_SAMPLE_STEP, dtype=np.int32)
    xs = np.arange(margin, w - margin, GLOBAL_SAMPLE_STEP, dtype=np.int32)
    cur = cy[np.ix_(ys, xs)].astype(np.int16)

    def score(dx: int, dy: int):
        ref = py[np.ix_(ys + dy, xs + dx)].astype(np.int16)
        return float(np.abs(cur - ref).mean())

    best = None
    best_key = None

    for dx, dy in _ordered_global_candidates(global_radius, GLOBAL_COARSE_STEP):
        cost = score(dx, dy)
        key = (
            cost,
            abs(dx) + abs(dy),
            abs(dy),
            abs(dx),
            dy,
            dx,
        )
        if best_key is None or key < best_key:
            best_key = key
            best = (dx, dy, cost)

    coarse_dx, coarse_dy, _ = best
    fine = []
    for dy in range(
        max(-global_radius, coarse_dy - GLOBAL_COARSE_STEP),
        min(global_radius, coarse_dy + GLOBAL_COARSE_STEP) + 1,
        GLOBAL_FINE_STEP,
    ):
        for dx in range(
            max(-global_radius, coarse_dx - GLOBAL_COARSE_STEP),
            min(global_radius, coarse_dx + GLOBAL_COARSE_STEP) + 1,
            GLOBAL_FINE_STEP,
        ):
            fine.append((dx, dy))
    fine = sorted(
        set(fine),
        key=lambda p: (
            abs(p[0] - coarse_dx) + abs(p[1] - coarse_dy),
            abs(p[1] - coarse_dy),
            abs(p[0] - coarse_dx),
            p[1],
            p[0],
        ),
    )

    for dx, dy in fine:
        cost = score(dx, dy)
        key = (
            cost,
            abs(dx) + abs(dy),
            abs(dy),
            abs(dx),
            dy,
            dx,
        )
        if key < best_key:
            best_key = key
            best = (dx, dy, cost)

    return best


def global_local_motion(
    frame: bytes,
    prev: bytes,
    w: int,
    h: int,
):
    cy, cu, cv = split_np(frame, w, h)
    py, pu, pv = split_np(prev, w, h)

    global_dx, global_dy, global_cost = estimate_global_translation(
        frame, prev, w, h
    )

    cand = local_candidates(LOCAL_RADIUS)
    if len(cand) != ZERO_FALLBACK_INDEX:
        raise RuntimeError("unexpected local candidate count")

    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2

    mv = bytearray(bh * bw)
    ry = np.empty_like(cy)
    ru = np.empty_like(cu)
    rv = np.empty_like(cv)

    local_abs_sum = 0
    local_blocks = 0
    fallback_blocks = 0

    k = 0
    for by in range(bh):
        y0 = by * BLOCK
        for bx in range(bw):
            x0 = bx * BLOCK
            cur = cy[y0:y0 + BLOCK, x0:x0 + BLOCK].astype(np.int16)

            best_index = ZERO_FALLBACK_INDEX
            best_dx = 0
            best_dy = 0
            zero_ref = py[y0:y0 + BLOCK, x0:x0 + BLOCK].astype(np.int16)
            best_cost = int(np.abs(cur - zero_ref).sum())

            for i, (ldx, ldy) in enumerate(cand):
                dx = global_dx + ldx
                dy = global_dy + ldy
                sx = x0 + dx
                sy = y0 + dy
                if (
                    sx < 0 or sy < 0
                    or sx + BLOCK > w
                    or sy + BLOCK > h
                ):
                    continue

                ref = py[
                    sy:sy + BLOCK,
                    sx:sx + BLOCK,
                ].astype(np.int16)
                cost = int(np.abs(cur - ref).sum())

                if cost < best_cost:
                    best_cost = cost
                    best_index = i
                    best_dx = dx
                    best_dy = dy

            mv[k] = best_index
            k += 1

            if best_index == ZERO_FALLBACK_INDEX:
                fallback_blocks += 1
            else:
                ldx, ldy = cand[best_index]
                local_abs_sum += abs(ldx) + abs(ldy)
                local_blocks += 1

            ref = py[
                y0 + best_dy:y0 + best_dy + BLOCK,
                x0 + best_dx:x0 + best_dx + BLOCK,
            ].astype(np.int16)
            ry[y0:y0 + BLOCK, x0:x0 + BLOCK] = (
                (cur - ref) & 255
            ).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2
            cdx = best_dx // 2
            cdy = best_dy // 2

            ucur = cu[cy0:cy0 + cb, cx0:cx0 + cb].astype(np.int16)
            vcur = cv[cy0:cy0 + cb, cx0:cx0 + cb].astype(np.int16)
            uref = pu[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)
            vref = pv[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)

            ru[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (ucur - uref) & 255
            ).astype(np.uint8)
            rv[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (vcur - vref) & 255
            ).astype(np.uint8)

    residual = ry.tobytes() + ru.tobytes() + rv.tobytes()
    stats = {
        "global_dx": global_dx,
        "global_dy": global_dy,
        "global_sample_mad": global_cost,
        "fallback_blocks": fallback_blocks,
        "mean_local_manhattan": (
            local_abs_sum / local_blocks if local_blocks else 0.0
        ),
    }
    return (global_dx, global_dy), bytes(mv), residual, stats


def global_local_inverse(
    global_dx: int,
    global_dy: int,
    mv: bytes,
    residual: bytes,
    prev: bytes,
    w: int,
    h: int,
):
    py, pu, pv = split_np(prev, w, h)
    ys, cs, cw, ch = frame_sizes(w, h)
    ry = np.frombuffer(residual[:ys], dtype=np.uint8).reshape(h, w)
    ru = np.frombuffer(residual[ys:ys + cs], dtype=np.uint8).reshape(ch, cw)
    rv = np.frombuffer(residual[ys + cs:], dtype=np.uint8).reshape(ch, cw)

    cand = local_candidates(LOCAL_RADIUS)
    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2
    if len(mv) != bh * bw:
        raise ValueError("bad global-local motion map")

    oy = np.empty_like(py)
    ou = np.empty_like(pu)
    ov = np.empty_like(pv)

    k = 0
    for by in range(bh):
        y0 = by * BLOCK
        for bx in range(bw):
            x0 = bx * BLOCK
            idx = mv[k]
            k += 1

            if idx == ZERO_FALLBACK_INDEX:
                dx = 0
                dy = 0
            elif idx < len(cand):
                ldx, ldy = cand[idx]
                dx = global_dx + ldx
                dy = global_dy + ldy
            else:
                raise ValueError("bad global-local vector index")

            sx = x0 + dx
            sy = y0 + dy
            if (
                sx < 0 or sy < 0
                or sx + BLOCK > w
                or sy + BLOCK > h
            ):
                raise ValueError("global-local motion vector out of bounds")

            ref = py[
                sy:sy + BLOCK,
                sx:sx + BLOCK,
            ].astype(np.int16)
            rr = ry[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)
            oy[y0:y0 + BLOCK, x0:x0 + BLOCK] = (
                (ref + rr) & 255
            ).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2
            cdx = dx // 2
            cdy = dy // 2

            uref = pu[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)
            vref = pv[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)
            urr = ru[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)
            vrr = rv[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)

            ou[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (uref + urr) & 255
            ).astype(np.uint8)
            ov[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (vref + vrr) & 255
            ).astype(np.uint8)

    return oy.tobytes() + ou.tobytes() + ov.tobytes()


def build_global_local_records(raw_chunk: bytes, w: int, h: int, gop: int):
    fs = k13.frame_size(w, h)
    total = len(raw_chunk) // fs
    chunks = []
    frame_stats = []
    residual_mag_sum = 0
    residual_mag_count = 0

    t0 = time.perf_counter()
    off = 0
    while off < total:
        n = min(gop, total - off)
        records = []
        prev = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]
            if prev is None:
                records.append(("I", spatial_frame(frame, w, h)))
            else:
                gv, mv, residual, stats = global_local_motion(
                    frame, prev, w, h
                )
                records.append(("P", gv, mv, residual))
                frame_stats.append(stats)
                residual_mag_sum += sum(
                    b if b < 128 else 256 - b for b in residual
                )
                residual_mag_count += len(residual)
            prev = frame

        chunks.append((n, records))
        off += n

    seconds = time.perf_counter() - t0
    mean_mag = (
        residual_mag_sum / residual_mag_count
        if residual_mag_count else 0.0
    )
    return chunks, frame_stats, mean_mag, seconds


def serialize_global_local(
    chunks,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    residual_mode: int,
):
    if residual_mode not in (GL_MOD8, GL_ZZ):
        raise ValueError("bad global-local residual mode")

    out = bytearray()
    out.extend(GL_HDR.pack(
        GL_MAGIC,
        GL_VERSION,
        FMT_YUV420P8,
        gop,
        BLOCK,
        LOCAL_RADIUS,
        GLOBAL_RADIUS,
        residual_mode,
        w,
        h,
        fpsn,
        fpsd,
    ))

    for n, records in chunks:
        payload = bytearray()
        for rec in records:
            if rec[0] == "I":
                payload.extend(rec[1])
            else:
                _, (gdx, gdy), mv, residual = rec
                payload.extend(GL_VEC.pack(gdx, gdy))
                payload.extend(mv)
                if residual_mode == GL_ZZ:
                    payload.extend(map_residual(residual, ZZ_INTER))
                else:
                    payload.extend(residual)

        p = bytes(payload)
        out.extend(GL_CHUNK.pack(n, len(p), zlib.crc32(p) & 0xFFFFFFFF))
        out.extend(p)

    return bytes(out)


def decode_global_local_front(front: bytes) -> bytes:
    if len(front) < GL_HDR.size:
        raise ValueError("truncated KSV-14 global-local header")

    (
        magic,
        version,
        fmt,
        gop,
        block,
        local_radius,
        global_radius,
        residual_mode,
        w,
        h,
        fpsn,
        fpsd,
    ) = GL_HDR.unpack_from(front, 0)

    if (
        magic != GL_MAGIC
        or version != GL_VERSION
        or fmt != FMT_YUV420P8
        or block != BLOCK
        or local_radius != LOCAL_RADIUS
        or global_radius != GLOBAL_RADIUS
        or residual_mode not in (GL_MOD8, GL_ZZ)
    ):
        raise ValueError("unsupported KSV-14 global-local stream")

    del fpsn, fpsd

    fs = k13.frame_size(w, h)
    mvn = (w // BLOCK) * (h // BLOCK)

    pos = GL_HDR.size
    out = bytearray()

    while pos < len(front):
        if pos + GL_CHUNK.size > len(front):
            raise ValueError("truncated global-local chunk header")

        n, size, crc = GL_CHUNK.unpack_from(front, pos)
        pos += GL_CHUNK.size
        if n < 1 or n > gop or pos + size > len(front):
            raise ValueError("bad global-local chunk")

        payload = front[pos:pos + size]
        pos += size

        if zlib.crc32(payload) & 0xFFFFFFFF != crc:
            raise ValueError("global-local CRC mismatch")

        q = 0
        prev = None

        for _ in range(n):
            if prev is None:
                if q + fs > len(payload):
                    raise ValueError("truncated global-local intra")
                spatial = payload[q:q + fs]
                q += fs
                frame = spatial_frame_inv(spatial, w, h)
            else:
                need = GL_VEC.size + mvn + fs
                if q + need > len(payload):
                    raise ValueError("truncated global-local inter")

                gdx, gdy = GL_VEC.unpack_from(payload, q)
                q += GL_VEC.size
                mv = payload[q:q + mvn]
                q += mvn
                mapped = payload[q:q + fs]
                q += fs

                residual = (
                    unmap_residual(mapped, ZZ_INTER)
                    if residual_mode == GL_ZZ
                    else mapped
                )
                frame = global_local_inverse(
                    gdx, gdy, mv, residual, prev, w, h
                )

            out.extend(frame)
            prev = frame

        if q != len(payload):
            raise ValueError("global-local trailing payload bytes")

    return bytes(out)


def global_local_candidates(
    raw_chunk: bytes,
    exe: Path,
    tmp: Path,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    tag: str,
):
    chunks, frame_stats, mean_mag, search_seconds = build_global_local_records(
        raw_chunk, w, h, gop
    )

    rows = []
    for residual_mode, label, outer_mode in (
        (GL_MOD8, "GL_MOD8", MODE_GL_MOD8),
        (GL_ZZ, "GL_ZZ", MODE_GL_ZZ),
    ):
        t0 = time.perf_counter()
        front = serialize_global_local(
            chunks, w, h, fpsn, fpsd, gop, residual_mode
        )
        serialization_seconds = time.perf_counter() - t0
        payload, backend_seconds = k13.compress_bytes(
            front, exe, tmp, f"{tag}.{label.lower()}"
        )
        rows.append({
            "mode": outer_mode,
            "label": label,
            "payload": payload,
            "frontend_seconds": search_seconds + serialization_seconds,
            "backend_seconds": backend_seconds,
            "mean_mag": mean_mag,
            "frame_stats": frame_stats,
        })

    return rows, search_seconds


def baseline_candidates(
    raw_chunk: bytes,
    exe: Path,
    tmp: Path,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    tag: str,
):
    temp = k13.temp_candidate(
        raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, tag
    )
    r4, r4_search_seconds = k13.radius_candidates(
        raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, k13.R4, tag
    )

    temp = dict(temp)
    temp["mode"] = MODE_TEMP
    temp["label"] = "TEMP"

    r4_mod = dict(r4[0])
    r4_mod["mode"] = MODE_R4_MOD8
    r4_mod["label"] = "MC_R4_MOD8"

    r4_zz = dict(r4[1])
    r4_zz["mode"] = MODE_R4_ZZ
    r4_zz["label"] = "MC_R4_ZZ"

    return temp, [r4_mod, r4_zz], r4_search_seconds


def choose(candidates):
    return min(
        candidates,
        key=lambda x: (
            len(x["payload"]),
            x["mode"],
        ),
    )


def write_outer(
    dst: Path,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    route_span: int,
    entries,
):
    with dst.open("wb") as f:
        f.write(OUTER_HDR.pack(
            OUTER_MAGIC,
            OUTER_VERSION,
            w,
            h,
            fpsn,
            fpsd,
            gop,
            route_span,
        ))
        for entry in entries:
            payload = entry["payload"]
            f.write(OUTER_ENT.pack(
                entry["mode"],
                entry["frames"],
                len(payload),
            ))
            f.write(payload)


def decode_outer(src: Path, dst: Path, exe: Path):
    data = src.read_bytes()
    if len(data) < OUTER_HDR.size:
        raise ValueError("truncated KSV-14 outer header")

    (
        magic,
        version,
        w,
        h,
        fpsn,
        fpsd,
        gop,
        route_span,
    ) = OUTER_HDR.unpack_from(data, 0)

    if magic != OUTER_MAGIC or version != OUTER_VERSION:
        raise ValueError("bad KSV-14 outer stream")

    del fpsn, fpsd, gop, route_span

    pos = OUTER_HDR.size
    out = bytearray()

    with tempfile.TemporaryDirectory(prefix="ksv14_dec_") as td:
        tmp = Path(td)
        idx = 0

        while pos < len(data):
            if pos + OUTER_ENT.size > len(data):
                raise ValueError("truncated KSV-14 outer entry")
            mode, frames, payload_size = OUTER_ENT.unpack_from(data, pos)
            pos += OUTER_ENT.size
            if pos + payload_size > len(data):
                raise ValueError("truncated KSV-14 outer payload")

            payload = data[pos:pos + payload_size]
            pos += payload_size

            arc = tmp / f"{idx}.aur"
            outdir = tmp / f"{idx}.out"
            front = tmp / f"{idx}.front"
            raw = tmp / f"{idx}.yuv"

            arc.write_bytes(payload)
            k13.kdp(exe, arc, outdir)
            files = [p for p in outdir.rglob("*") if p.is_file()]
            if len(files) != 1:
                raise RuntimeError("unexpected KHEPRI decode output")
            shutil.copyfile(files[0], front)

            if mode == MODE_TEMP:
                from kstream_video_baseline import decode_file as temp_decode
                temp_decode(front, raw)
                chunk = raw.read_bytes()
            elif mode == MODE_R4_MOD8:
                mc_decode(front, raw)
                chunk = raw.read_bytes()
            elif mode == MODE_R4_ZZ:
                zz_decode(front, raw, k13.R4)
                chunk = raw.read_bytes()
            elif mode in (MODE_GL_MOD8, MODE_GL_ZZ):
                chunk = decode_global_local_front(front.read_bytes())
            else:
                raise ValueError("unknown KSV-14 outer mode")

            if len(chunk) != frames * k13.frame_size(w, h):
                raise ValueError("KSV-14 decoded frame count mismatch")

            out.extend(chunk)
            idx += 1

    dst.write_bytes(out)


def policy_stats(entries):
    return dict(sorted(Counter(e["label"] for e in entries).items()))


def summarize_global_stats(gl_candidates):
    stats = []
    for candidate in gl_candidates:
        stats.extend(candidate.get("frame_stats", []))

    # Both GL candidates share the same frame_stats object; de-duplicate by
    # taking the first candidate only.
    if gl_candidates:
        stats = gl_candidates[0].get("frame_stats", [])

    if not stats:
        return {
            "mean_global_manhattan": 0.0,
            "max_global_manhattan": 0,
            "mean_fallback_blocks": 0.0,
            "mean_local_manhattan": 0.0,
        }

    mags = [abs(s["global_dx"]) + abs(s["global_dy"]) for s in stats]
    return {
        "mean_global_manhattan": float(sum(mags) / len(mags)),
        "max_global_manhattan": int(max(mags)),
        "mean_fallback_blocks": float(
            sum(s["fallback_blocks"] for s in stats) / len(stats)
        ),
        "mean_local_manhattan": float(
            sum(s["mean_local_manhattan"] for s in stats) / len(stats)
        ),
    }


def encode_source(
    src: Path,
    prefix: Path,
    exe: Path,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int = 10,
    route_span: int = 20,
):
    raw = src.read_bytes()
    fs = k13.frame_size(w, h)
    if len(raw) % fs:
        raise ValueError("incomplete source frames")

    total = len(raw) // fs
    baseline_entries = []
    gl_entries = []
    oracle_entries = []
    windows = []

    baseline_research_seconds = 0.0
    gl_research_seconds = 0.0
    oracle_research_seconds = 0.0

    with tempfile.TemporaryDirectory(prefix="ksv14_enc_") as td:
        tmp = Path(td)

        for gi, off in enumerate(range(0, total, route_span)):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, r4, r4_search_s = baseline_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )
            gl, gl_search_s = global_local_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )

            baseline = choose([temp, *r4])
            global_local = choose([temp, *gl])
            oracle = choose([temp, *r4, *gl])

            for entry in (baseline, global_local, oracle):
                entry["frames"] = n

            baseline_entries.append(dict(baseline))
            gl_entries.append(dict(global_local))
            oracle_entries.append(dict(oracle))

            temp_cost = temp["frontend_seconds"] + temp["backend_seconds"]
            r4_cost = r4_search_s + sum(x["backend_seconds"] for x in r4)
            gl_cost = gl_search_s + sum(x["backend_seconds"] for x in gl)

            baseline_research_seconds += temp_cost + r4_cost
            gl_research_seconds += temp_cost + gl_cost
            oracle_research_seconds += temp_cost + r4_cost + gl_cost

            gl_stats = summarize_global_stats(gl)
            windows.append({
                "window": gi,
                "frames": n,
                "temp_bytes": len(temp["payload"]),
                "r4_mod8_bytes": len(r4[0]["payload"]),
                "r4_zz_bytes": len(r4[1]["payload"]),
                "gl_mod8_bytes": len(gl[0]["payload"]),
                "gl_zz_bytes": len(gl[1]["payload"]),
                "baseline_selected": baseline["label"],
                "global_local_selected": global_local["label"],
                "oracle_selected": oracle["label"],
                "gl_mean_residual_mag": gl[0]["mean_mag"],
                **gl_stats,
            })

    paths = {
        "baseline": prefix.with_suffix(".baseline.k14"),
        "global_local": prefix.with_suffix(".global_local.k14"),
        "oracle": prefix.with_suffix(".oracle.k14"),
    }

    write_outer(
        paths["baseline"], w, h, fpsn, fpsd, gop, route_span, baseline_entries
    )
    write_outer(
        paths["global_local"], w, h, fpsn, fpsd, gop, route_span, gl_entries
    )
    write_outer(
        paths["oracle"], w, h, fpsn, fpsd, gop, route_span, oracle_entries
    )

    return {
        "paths": paths,
        "baseline": {
            "bytes": paths["baseline"].stat().st_size,
            "encode_research_seconds": baseline_research_seconds,
            "modes": policy_stats(baseline_entries),
        },
        "global_local": {
            "bytes": paths["global_local"].stat().st_size,
            "encode_research_seconds": gl_research_seconds,
            "modes": policy_stats(gl_entries),
        },
        "oracle": {
            "bytes": paths["oracle"].stat().st_size,
            "encode_research_seconds": oracle_research_seconds,
            "modes": policy_stats(oracle_entries),
        },
        "windows": windows,
    }


def parse_clip(spec: str):
    parts = spec.split(":")
    if len(parts) != 6:
        raise argparse.ArgumentTypeError(
            "--clip must be name:path:width:height:fps_num:fps_den"
        )
    return {
        "name": parts[0],
        "path": Path(parts[1]).resolve(),
        "w": int(parts[2]),
        "h": int(parts[3]),
        "fpsn": int(parts[4]),
        "fpsd": int(parts[5]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kephir", type=Path, required=True)
    ap.add_argument("--clip", action="append", type=parse_clip, required=True)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for clip in args.clip:
        src = clip["path"]
        encoded = encode_source(
            src,
            OUT / clip["name"],
            args.kephir,
            clip["w"],
            clip["h"],
            clip["fpsn"],
            clip["fpsd"],
        )

        decoded = {}
        for policy in ("baseline", "global_local", "oracle"):
            dst = OUT / f"{clip['name']}.{policy}.decoded.yuv"
            t0 = time.perf_counter()
            decode_outer(encoded["paths"][policy], dst, args.kephir)
            seconds = time.perf_counter() - t0
            ok = k13.sha_file(dst) == k13.sha_file(src)
            if not ok:
                raise RuntimeError(
                    f"{clip['name']} {policy}: SHA mismatch"
                )
            decoded[policy] = {
                "decode_seconds": seconds,
                "sha_ok": True,
            }

        raw_bytes = src.stat().st_size
        row = {
            "name": clip["name"],
            "raw_bytes": raw_bytes,
            "sha256": k13.sha_file(src),
            "baseline": {
                **encoded["baseline"],
                **decoded["baseline"],
            },
            "global_local": {
                **encoded["global_local"],
                **decoded["global_local"],
            },
            "oracle": {
                **encoded["oracle"],
                **decoded["oracle"],
            },
            "windows": encoded["windows"],
        }

        for policy in ("baseline", "global_local", "oracle"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        row["global_local_delta_bytes"] = (
            row["global_local"]["bytes"] - row["baseline"]["bytes"]
        )
        row["global_local_delta_percent"] = (
            100.0 * (
                row["global_local"]["bytes"] / row["baseline"]["bytes"] - 1.0
            )
        )
        row["oracle_delta_bytes"] = (
            row["oracle"]["bytes"] - row["baseline"]["bytes"]
        )
        row["oracle_delta_percent"] = (
            100.0 * (
                row["oracle"]["bytes"] / row["baseline"]["bytes"] - 1.0
            )
        )

        rows.append(row)
        print(
            "KSV14_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "global_local", row["global_local"]["bytes"],
            "oracle", row["oracle"]["bytes"],
            "gl_delta_pct", f"{row['global_local_delta_percent']:.6f}",
            "oracle_delta_pct", f"{row['oracle_delta_percent']:.6f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)
    aggregate = {}

    for policy in ("baseline", "global_local", "oracle"):
        total = sum(r[policy]["bytes"] for r in rows)
        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": 100.0 * total / raw_total,
            "encode_research_seconds": sum(
                r[policy]["encode_research_seconds"] for r in rows
            ),
        }

    aggregate["global_local_delta_bytes"] = (
        aggregate["global_local"]["bytes"] - aggregate["baseline"]["bytes"]
    )
    aggregate["global_local_delta_percent"] = (
        100.0 * (
            aggregate["global_local"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )
    aggregate["oracle_delta_bytes"] = (
        aggregate["oracle"]["bytes"] - aggregate["baseline"]["bytes"]
    )
    aggregate["oracle_delta_percent"] = (
        100.0 * (
            aggregate["oracle"]["bytes"] / aggregate["baseline"]["bytes"] - 1.0
        )
    )

    result = {
        "experiment": "KSV-14 global translation + local motion",
        "global_radius": GLOBAL_RADIUS,
        "global_coarse_step": GLOBAL_COARSE_STEP,
        "global_fine_step": GLOBAL_FINE_STEP,
        "global_sample_step": GLOBAL_SAMPLE_STEP,
        "local_radius": LOCAL_RADIUS,
        "block": BLOCK,
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "Global translation is estimated from sparse luma samples.",
            "Local motion remains the ordered 25-candidate ±4 field around the global vector.",
            "A reserved map code provides absolute zero-motion fallback at borders.",
            "Baseline matches the KSV-13 TEMP/R4 routing candidate set.",
            "Oracle is research-only and compares baseline plus global-local candidates.",
            "Every emitted stream is independently decoded and SHA verified.",
        ],
    }

    (OUT / "KSV14_RESULTS.json").write_text(json.dumps(result, indent=2))

    print("KSV14_GLOBAL_LOCAL_PASS")
    print(
        "KSV14_AGGREGATE",
        "baseline", aggregate["baseline"]["bytes"],
        "global_local", aggregate["global_local"]["bytes"],
        "oracle", aggregate["oracle"]["bytes"],
        "gl_delta_pct", f"{aggregate['global_local_delta_percent']:.6f}",
        "oracle_delta_pct", f"{aggregate['oracle_delta_percent']:.6f}",
    )


if __name__ == "__main__":
    main()
