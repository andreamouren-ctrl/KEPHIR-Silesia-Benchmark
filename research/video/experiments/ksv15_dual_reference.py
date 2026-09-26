#!/usr/bin/env python3
"""
KSV-15 Dual-Reference Temporal Motion.

Research hypothesis:
AURORA's remaining natural-video gap may come from forcing every inter block
to reference only the immediately previous frame.

KSV-15 adds a second already-decoded reference:
- ref0: previous frame
- ref1: frame two positions back, when available inside the GOP

Each 8x8 luma block searches the same ordered MC8R4 candidate set on both
references. Motion-map codes:
- 0..24  = ref0 + local candidate
- 25..49 = ref1 + local candidate

The first minimum wins, so equal-cost ties prefer the previous frame.

Policies emitted:
- baseline: TEMP / MC8R4 MOD8 / MC8R4 ZZ_INTER
- dual: TEMP / dual-ref MOD8 / dual-ref ZZ_INTER
- oracle: best of all baseline + dual candidates

All streams are independently decoded and SHA-verified.
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
from kstream_video_baseline import (
    decode_file as temp_decode,
)
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

OUT = Path("results/video/ksv15_dual_reference")

BLOCK = 8
RADIUS = 4
REF0_BASE = 0
REF1_BASE = 25
CANDIDATES_PER_REF = 25

FMT_YUV420P8 = 1

DUAL_MAGIC = b"K15D"
DUAL_VERSION = 1
DUAL_MOD8 = 0
DUAL_ZZ = 1
DUAL_HDR = struct.Struct("<4sBBBBBHHII")
DUAL_CHUNK = struct.Struct("<III")

OUTER_MAGIC = b"K15O"
OUTER_VERSION = 1
OUTER_HDR = struct.Struct("<4sBHHIIII")
OUTER_ENT = struct.Struct("<BII")

MODE_TEMP = 0
MODE_R4_MOD8 = 1
MODE_R4_ZZ = 2
MODE_DUAL_MOD8 = 3
MODE_DUAL_ZZ = 4


def split_np(frame: bytes, w: int, h: int):
    y, u, v, cw, ch = split_frame(frame, w, h)
    return (
        np.frombuffer(y, dtype=np.uint8).reshape(h, w),
        np.frombuffer(u, dtype=np.uint8).reshape(ch, cw),
        np.frombuffer(v, dtype=np.uint8).reshape(ch, cw),
    )


def _candidate_search(
    cur_y,
    ref_y,
    x0: int,
    y0: int,
    w: int,
    h: int,
    cand,
):
    cur = cur_y[y0:y0 + BLOCK, x0:x0 + BLOCK].astype(np.int16)
    best = None
    for idx, (dx, dy) in enumerate(cand):
        sx = x0 + dx
        sy = y0 + dy
        if (
            sx < 0
            or sy < 0
            or sx + BLOCK > w
            or sy + BLOCK > h
        ):
            continue
        ref = ref_y[
            sy:sy + BLOCK,
            sx:sx + BLOCK,
        ].astype(np.int16)
        cost = int(np.abs(cur - ref).sum())
        if best is None or cost < best[0]:
            best = (cost, idx, dx, dy)
            if cost == 0:
                break
    if best is None:
        raise RuntimeError("dual-reference search found no valid candidate")
    return best


def dual_motion_residual(
    frame: bytes,
    prev1: bytes,
    prev2: bytes | None,
    w: int,
    h: int,
):
    cy, cu, cv = split_np(frame, w, h)
    p1y, p1u, p1v = split_np(prev1, w, h)
    if prev2 is not None:
        p2y, p2u, p2v = split_np(prev2, w, h)
    else:
        p2y = p2u = p2v = None

    cand = local_candidates(RADIUS)
    if len(cand) != CANDIDATES_PER_REF:
        raise RuntimeError("unexpected MC8R4 candidate count")

    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2

    motion = bytearray(bh * bw)
    ry = np.empty_like(cy)
    ru = np.empty_like(cu)
    rv = np.empty_like(cv)

    ref1_blocks = 0
    ref2_blocks = 0
    ref2_gain_sum = 0
    ref2_gain_count = 0

    k = 0
    for by in range(bh):
        y0 = by * BLOCK
        for bx in range(bw):
            x0 = bx * BLOCK

            b1 = _candidate_search(cy, p1y, x0, y0, w, h, cand)
            best_cost, best_idx, best_dx, best_dy = b1
            best_ref = 0

            if p2y is not None:
                b2 = _candidate_search(cy, p2y, x0, y0, w, h, cand)
                if b2[0] < best_cost:
                    ref2_gain_sum += best_cost - b2[0]
                    ref2_gain_count += 1
                    best_cost, idx2, best_dx, best_dy = b2
                    best_idx = REF1_BASE + idx2
                    best_ref = 1

            motion[k] = best_idx
            k += 1

            if best_ref == 0:
                ref1_blocks += 1
                ref_y, ref_u, ref_v = p1y, p1u, p1v
            else:
                ref2_blocks += 1
                ref_y, ref_u, ref_v = p2y, p2u, p2v

            cur = cy[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)
            pred = ref_y[
                y0 + best_dy:y0 + best_dy + BLOCK,
                x0 + best_dx:x0 + best_dx + BLOCK,
            ].astype(np.int16)
            ry[y0:y0 + BLOCK, x0:x0 + BLOCK] = (
                (cur - pred) & 255
            ).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2
            cdx = best_dx // 2
            cdy = best_dy // 2

            ucur = cu[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)
            vcur = cv[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)
            upred = ref_u[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)
            vpred = ref_v[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)

            ru[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (ucur - upred) & 255
            ).astype(np.uint8)
            rv[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (vcur - vpred) & 255
            ).astype(np.uint8)

    residual = ry.tobytes() + ru.tobytes() + rv.tobytes()
    total_blocks = ref1_blocks + ref2_blocks
    return bytes(motion), residual, {
        "ref1_blocks": ref1_blocks,
        "ref2_blocks": ref2_blocks,
        "ref2_fraction": (
            ref2_blocks / total_blocks if total_blocks else 0.0
        ),
        "mean_ref2_sad_gain": (
            ref2_gain_sum / ref2_gain_count
            if ref2_gain_count else 0.0
        ),
    }


def dual_motion_inverse(
    motion: bytes,
    residual: bytes,
    prev1: bytes,
    prev2: bytes | None,
    w: int,
    h: int,
):
    p1y, p1u, p1v = split_np(prev1, w, h)
    if prev2 is not None:
        p2y, p2u, p2v = split_np(prev2, w, h)
    else:
        p2y = p2u = p2v = None

    ys, cs, cw, ch = frame_sizes(w, h)
    ry = np.frombuffer(
        residual[:ys], dtype=np.uint8
    ).reshape(h, w)
    ru = np.frombuffer(
        residual[ys:ys + cs], dtype=np.uint8
    ).reshape(ch, cw)
    rv = np.frombuffer(
        residual[ys + cs:], dtype=np.uint8
    ).reshape(ch, cw)

    cand = local_candidates(RADIUS)
    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2
    if len(motion) != bh * bw:
        raise ValueError("bad dual-reference motion map")

    oy = np.empty_like(p1y)
    ou = np.empty_like(p1u)
    ov = np.empty_like(p1v)

    k = 0
    for by in range(bh):
        y0 = by * BLOCK
        for bx in range(bw):
            x0 = bx * BLOCK
            code = motion[k]
            k += 1

            if code < REF1_BASE:
                ref = 0
                idx = code
            else:
                ref = 1
                idx = code - REF1_BASE

            if idx >= len(cand):
                raise ValueError("bad dual-reference candidate index")
            if ref == 1 and prev2 is None:
                raise ValueError("dual-reference uses unavailable ref2")

            dx, dy = cand[idx]
            sx = x0 + dx
            sy = y0 + dy
            if (
                sx < 0
                or sy < 0
                or sx + BLOCK > w
                or sy + BLOCK > h
            ):
                raise ValueError("dual-reference vector out of bounds")

            if ref == 0:
                ref_y, ref_u, ref_v = p1y, p1u, p1v
            else:
                ref_y, ref_u, ref_v = p2y, p2u, p2v

            pred = ref_y[
                sy:sy + BLOCK,
                sx:sx + BLOCK,
            ].astype(np.int16)
            rr = ry[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)
            oy[y0:y0 + BLOCK, x0:x0 + BLOCK] = (
                (pred + rr) & 255
            ).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2
            cdx = dx // 2
            cdy = dy // 2

            upred = ref_u[
                cy0 + cdy:cy0 + cdy + cb,
                cx0 + cdx:cx0 + cdx + cb,
            ].astype(np.int16)
            vpred = ref_v[
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
                (upred + urr) & 255
            ).astype(np.uint8)
            ov[cy0:cy0 + cb, cx0:cx0 + cb] = (
                (vpred + vrr) & 255
            ).astype(np.uint8)

    return oy.tobytes() + ou.tobytes() + ov.tobytes()


def build_dual_records(raw_chunk: bytes, w: int, h: int, gop: int):
    fs = k13.frame_size(w, h)
    total = len(raw_chunk) // fs
    chunks = []
    stats = []
    residual_mag_sum = 0
    residual_mag_count = 0

    t0 = time.perf_counter()
    off = 0
    while off < total:
        n = min(gop, total - off)
        records = []
        prev1 = None
        prev2 = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]
            if prev1 is None:
                records.append(("I", spatial_frame(frame, w, h)))
            else:
                motion, residual, st = dual_motion_residual(
                    frame, prev1, prev2, w, h
                )
                records.append(("P", motion, residual))
                stats.append(st)
                residual_mag_sum += sum(
                    b if b < 128 else 256 - b for b in residual
                )
                residual_mag_count += len(residual)

            prev2 = prev1
            prev1 = frame

        chunks.append((n, records))
        off += n

    seconds = time.perf_counter() - t0
    return chunks, stats, (
        residual_mag_sum / residual_mag_count
        if residual_mag_count else 0.0
    ), seconds


def serialize_dual(
    chunks,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    residual_mode: int,
):
    if residual_mode not in (DUAL_MOD8, DUAL_ZZ):
        raise ValueError("bad dual-reference residual mode")

    out = bytearray()
    out.extend(DUAL_HDR.pack(
        DUAL_MAGIC,
        DUAL_VERSION,
        FMT_YUV420P8,
        gop,
        BLOCK,
        RADIUS,
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
                _, motion, residual = rec
                payload.extend(motion)
                payload.extend(
                    map_residual(residual, ZZ_INTER)
                    if residual_mode == DUAL_ZZ
                    else residual
                )

        p = bytes(payload)
        out.extend(DUAL_CHUNK.pack(
            n, len(p), zlib.crc32(p) & 0xFFFFFFFF
        ))
        out.extend(p)

    return bytes(out)


def decode_dual_front(front: bytes) -> bytes:
    if len(front) < DUAL_HDR.size:
        raise ValueError("truncated KSV-15 header")

    (
        magic,
        version,
        fmt,
        gop,
        block,
        radius,
        w,
        h,
        fpsn,
        fpsd,
    ) = DUAL_HDR.unpack_from(front, 0)

    if (
        magic != DUAL_MAGIC
        or version != DUAL_VERSION
        or fmt != FMT_YUV420P8
        or block != BLOCK
        or radius != RADIUS
    ):
        raise ValueError("unsupported KSV-15 dual-reference stream")

    del fpsn, fpsd

    fs = k13.frame_size(w, h)
    mvn = (w // BLOCK) * (h // BLOCK)

    pos = DUAL_HDR.size
    out = bytearray()

    while pos < len(front):
        if pos + DUAL_CHUNK.size > len(front):
            raise ValueError("truncated KSV-15 chunk header")

        n, size, crc = DUAL_CHUNK.unpack_from(front, pos)
        pos += DUAL_CHUNK.size
        if n < 1 or n > gop or pos + size > len(front):
            raise ValueError("bad KSV-15 chunk")

        payload = front[pos:pos + size]
        pos += size
        if zlib.crc32(payload) & 0xFFFFFFFF != crc:
            raise ValueError("KSV-15 CRC mismatch")

        q = 0
        prev1 = None
        prev2 = None

        for _ in range(n):
            if prev1 is None:
                if q + fs > len(payload):
                    raise ValueError("truncated KSV-15 intra")
                spatial = payload[q:q + fs]
                q += fs
                frame = spatial_frame_inv(spatial, w, h)
            else:
                if q + mvn + fs > len(payload):
                    raise ValueError("truncated KSV-15 inter")
                motion = payload[q:q + mvn]
                q += mvn
                mapped = payload[q:q + fs]
                q += fs

                # Residual mode is inferred from the file name by the outer
                # wrapper, so this routine receives a globally set attribute.
                residual = (
                    unmap_residual(mapped, ZZ_INTER)
                    if decode_dual_front.residual_mode == DUAL_ZZ
                    else mapped
                )
                frame = dual_motion_inverse(
                    motion, residual, prev1, prev2, w, h
                )

            out.extend(frame)
            prev2 = prev1
            prev1 = frame

        if q != len(payload):
            raise ValueError("KSV-15 trailing payload bytes")

    return bytes(out)


decode_dual_front.residual_mode = DUAL_MOD8


def dual_candidates(
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
    chunks, stats, mean_mag, search_seconds = build_dual_records(
        raw_chunk, w, h, gop
    )

    rows = []
    for residual_mode, label, outer_mode in (
        (DUAL_MOD8, "DUAL_MOD8", MODE_DUAL_MOD8),
        (DUAL_ZZ, "DUAL_ZZ", MODE_DUAL_ZZ),
    ):
        t0 = time.perf_counter()
        front = serialize_dual(
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
            "frame_stats": stats,
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
        key=lambda x: (len(x["payload"]), x["mode"])
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
        raise ValueError("truncated KSV-15 outer header")

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
        raise ValueError("bad KSV-15 outer stream")

    del fpsn, fpsd, gop, route_span

    pos = OUTER_HDR.size
    out = bytearray()

    with tempfile.TemporaryDirectory(prefix="ksv15_dec_") as td:
        tmp = Path(td)
        idx = 0

        while pos < len(data):
            if pos + OUTER_ENT.size > len(data):
                raise ValueError("truncated KSV-15 outer entry")

            mode, frames, payload_size = OUTER_ENT.unpack_from(data, pos)
            pos += OUTER_ENT.size
            if pos + payload_size > len(data):
                raise ValueError("truncated KSV-15 outer payload")

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
                temp_decode(front, raw)
                chunk = raw.read_bytes()
            elif mode == MODE_R4_MOD8:
                mc_decode(front, raw)
                chunk = raw.read_bytes()
            elif mode == MODE_R4_ZZ:
                zz_decode(front, raw, k13.R4)
                chunk = raw.read_bytes()
            elif mode == MODE_DUAL_MOD8:
                decode_dual_front.residual_mode = DUAL_MOD8
                chunk = decode_dual_front(front.read_bytes())
            elif mode == MODE_DUAL_ZZ:
                decode_dual_front.residual_mode = DUAL_ZZ
                chunk = decode_dual_front(front.read_bytes())
            else:
                raise ValueError("unknown KSV-15 outer mode")

            if len(chunk) != frames * k13.frame_size(w, h):
                raise ValueError("KSV-15 decoded frame count mismatch")

            out.extend(chunk)
            idx += 1

    dst.write_bytes(out)


def policy_stats(entries):
    return dict(sorted(Counter(e["label"] for e in entries).items()))


def summarize_dual_stats(dual_rows):
    stats = dual_rows[0].get("frame_stats", []) if dual_rows else []
    if not stats:
        return {
            "mean_ref2_fraction": 0.0,
            "max_ref2_fraction": 0.0,
            "mean_ref2_sad_gain": 0.0,
        }

    return {
        "mean_ref2_fraction": float(
            sum(s["ref2_fraction"] for s in stats) / len(stats)
        ),
        "max_ref2_fraction": float(
            max(s["ref2_fraction"] for s in stats)
        ),
        "mean_ref2_sad_gain": float(
            sum(s["mean_ref2_sad_gain"] for s in stats) / len(stats)
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
    dual_entries = []
    oracle_entries = []
    windows = []

    baseline_research_seconds = 0.0
    dual_research_seconds = 0.0
    oracle_research_seconds = 0.0

    with tempfile.TemporaryDirectory(prefix="ksv15_enc_") as td:
        tmp = Path(td)

        for gi, off in enumerate(range(0, total, route_span)):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, r4, r4_search_seconds = baseline_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )
            dual, dual_search_seconds = dual_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )

            baseline = choose([temp, *r4])
            dual_policy = choose([temp, *dual])
            oracle = choose([temp, *r4, *dual])

            for entry in (baseline, dual_policy, oracle):
                entry["frames"] = n

            baseline_entries.append(dict(baseline))
            dual_entries.append(dict(dual_policy))
            oracle_entries.append(dict(oracle))

            temp_cost = temp["frontend_seconds"] + temp["backend_seconds"]
            r4_cost = (
                r4_search_seconds
                + sum(x["backend_seconds"] for x in r4)
            )
            dual_cost = (
                dual_search_seconds
                + sum(x["backend_seconds"] for x in dual)
            )

            baseline_research_seconds += temp_cost + r4_cost
            dual_research_seconds += temp_cost + dual_cost
            oracle_research_seconds += temp_cost + r4_cost + dual_cost

            stats = summarize_dual_stats(dual)
            windows.append({
                "window": gi,
                "frames": n,
                "temp_bytes": len(temp["payload"]),
                "r4_mod8_bytes": len(r4[0]["payload"]),
                "r4_zz_bytes": len(r4[1]["payload"]),
                "dual_mod8_bytes": len(dual[0]["payload"]),
                "dual_zz_bytes": len(dual[1]["payload"]),
                "baseline_selected": baseline["label"],
                "dual_selected": dual_policy["label"],
                "oracle_selected": oracle["label"],
                "dual_mean_residual_mag": dual[0]["mean_mag"],
                **stats,
            })

    paths = {
        "baseline": prefix.with_suffix(".baseline.k15"),
        "dual": prefix.with_suffix(".dual.k15"),
        "oracle": prefix.with_suffix(".oracle.k15"),
    }

    write_outer(
        paths["baseline"],
        w, h, fpsn, fpsd, gop, route_span,
        baseline_entries,
    )
    write_outer(
        paths["dual"],
        w, h, fpsn, fpsd, gop, route_span,
        dual_entries,
    )
    write_outer(
        paths["oracle"],
        w, h, fpsn, fpsd, gop, route_span,
        oracle_entries,
    )

    return {
        "paths": paths,
        "baseline": {
            "bytes": paths["baseline"].stat().st_size,
            "encode_research_seconds": baseline_research_seconds,
            "modes": policy_stats(baseline_entries),
        },
        "dual": {
            "bytes": paths["dual"].stat().st_size,
            "encode_research_seconds": dual_research_seconds,
            "modes": policy_stats(dual_entries),
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
        for policy in ("baseline", "dual", "oracle"):
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
            "dual": {
                **encoded["dual"],
                **decoded["dual"],
            },
            "oracle": {
                **encoded["oracle"],
                **decoded["oracle"],
            },
            "windows": encoded["windows"],
        }

        for policy in ("baseline", "dual", "oracle"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        row["dual_delta_bytes"] = (
            row["dual"]["bytes"] - row["baseline"]["bytes"]
        )
        row["dual_delta_percent"] = (
            100.0 * (
                row["dual"]["bytes"] / row["baseline"]["bytes"] - 1.0
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
            "KSV15_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "dual", row["dual"]["bytes"],
            "oracle", row["oracle"]["bytes"],
            "dual_delta_pct", f"{row['dual_delta_percent']:.6f}",
            "oracle_delta_pct", f"{row['oracle_delta_percent']:.6f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)
    aggregate = {}

    for policy in ("baseline", "dual", "oracle"):
        total = sum(r[policy]["bytes"] for r in rows)
        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": 100.0 * total / raw_total,
            "encode_research_seconds": sum(
                r[policy]["encode_research_seconds"] for r in rows
            ),
        }

    aggregate["dual_delta_bytes"] = (
        aggregate["dual"]["bytes"] - aggregate["baseline"]["bytes"]
    )
    aggregate["dual_delta_percent"] = (
        100.0 * (
            aggregate["dual"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )
    aggregate["oracle_delta_bytes"] = (
        aggregate["oracle"]["bytes"] - aggregate["baseline"]["bytes"]
    )
    aggregate["oracle_delta_percent"] = (
        100.0 * (
            aggregate["oracle"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )

    result = {
        "experiment": "KSV-15 dual-reference temporal motion",
        "references": ["previous", "two_frames_back"],
        "block": BLOCK,
        "radius": RADIUS,
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "Reference selection is encoded directly in the one-byte motion map.",
            "Equal-SAD ties prefer the immediately previous frame.",
            "The second reference never crosses the GOP intra reset.",
            "Baseline matches the KSV-13 TEMP/R4 routing candidate set.",
            "Oracle is research-only and compares baseline plus dual-reference candidates.",
            "Every emitted stream is independently decoded and SHA verified.",
        ],
    }

    (OUT / "KSV15_RESULTS.json").write_text(json.dumps(result, indent=2))

    print("KSV15_DUAL_REFERENCE_PASS")
    print(
        "KSV15_AGGREGATE",
        "baseline", aggregate["baseline"]["bytes"],
        "dual", aggregate["dual"]["bytes"],
        "oracle", aggregate["oracle"]["bytes"],
        "dual_delta_pct", f"{aggregate['dual_delta_percent']:.6f}",
        "oracle_delta_pct", f"{aggregate['oracle_delta_percent']:.6f}",
    )


if __name__ == "__main__":
    main()
