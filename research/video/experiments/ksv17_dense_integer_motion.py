#!/usr/bin/env python3
"""
KSV-17 Dense Integer Motion.

Research question:
does AURORA Media lose natural-video compression because MC8R4 samples motion
only every two luma pixels?

Current sparse MC8R4 at radius 4 evaluates:
    {-4,-2,0,+2,+4} x {-4,-2,0,+2,+4} = 25 vectors.

KSV-17 evaluates every integer displacement:
    [-4,+4] x [-4,+4] = 81 vectors.

81 candidates still fit in the existing one-byte motion-map budget.

Because YUV420 chroma has half luma resolution, odd luma displacement needs a
deterministic integer chroma predictor. Two policies are tested from the same
dense luma search:
- FLOOR: Python floor division d//2;
- TRUNC: truncation toward zero int(d/2).

Policies emitted:
- baseline: TEMP / sparse MC8R4 MOD8 / sparse MC8R4 ZZ_INTER;
- dense: TEMP / dense FLOOR+TRUNC, each MOD8+ZZ_INTER;
- oracle: best of baseline + all dense candidates.

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
from kstream_video_baseline import decode_file as temp_decode
from kstream_video_motion_control import (
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

OUT = Path("results/video/ksv17_dense_integer")

BLOCK = 8
RADIUS = 4

CHROMA_FLOOR = 0
CHROMA_TRUNC = 1

DENSE_MOD8 = 0
DENSE_ZZ = 1

FMT_YUV420P8 = 1

DENSE_MAGIC = b"K17D"
DENSE_VERSION = 1
DENSE_HDR = struct.Struct("<4sBBBBBBBHHII")
DENSE_CHUNK = struct.Struct("<III")

OUTER_MAGIC = b"K17O"
OUTER_VERSION = 1
OUTER_HDR = struct.Struct("<4sBHHIIII")
OUTER_ENT = struct.Struct("<BII")

MODE_TEMP = 0
MODE_R4_MOD8 = 1
MODE_R4_ZZ = 2
MODE_DENSE_FLOOR_MOD8 = 3
MODE_DENSE_FLOOR_ZZ = 4
MODE_DENSE_TRUNC_MOD8 = 5
MODE_DENSE_TRUNC_ZZ = 6


def dense_candidates(radius: int = RADIUS):
    values = range(-radius, radius + 1)
    out = [(dx, dy) for dy in values for dx in values]
    out.sort(
        key=lambda p: (
            abs(p[0]) + abs(p[1]),
            abs(p[1]),
            abs(p[0]),
            p[1],
            p[0],
        )
    )
    if len(out) > 256:
        raise RuntimeError("dense candidate set no longer fits one byte")
    return out


DENSE_CANDIDATES = dense_candidates()


def split_np(frame: bytes, w: int, h: int):
    y, u, v, cw, ch = split_frame(frame, w, h)
    return (
        np.frombuffer(y, dtype=np.uint8).reshape(h, w),
        np.frombuffer(u, dtype=np.uint8).reshape(ch, cw),
        np.frombuffer(v, dtype=np.uint8).reshape(ch, cw),
    )


def chroma_shift(value: int, policy: int) -> int:
    if policy == CHROMA_FLOOR:
        return value // 2
    if policy == CHROMA_TRUNC:
        return int(value / 2)
    raise ValueError("unknown dense chroma policy")


def _best_dense_luma(
    current_y: np.ndarray,
    previous_y: np.ndarray,
    x0: int,
    y0: int,
    w: int,
    h: int,
):
    cur = current_y[
        y0:y0 + BLOCK,
        x0:x0 + BLOCK,
    ].astype(np.int16)

    best = None

    for index, (dx, dy) in enumerate(DENSE_CANDIDATES):
        sx = x0 + dx
        sy = y0 + dy
        if (
            sx < 0
            or sy < 0
            or sx + BLOCK > w
            or sy + BLOCK > h
        ):
            continue

        ref = previous_y[
            sy:sy + BLOCK,
            sx:sx + BLOCK,
        ].astype(np.int16)

        cost = int(np.abs(cur - ref).sum())

        if best is None or cost < best[0]:
            best = (cost, index, dx, dy)
            if cost == 0:
                break

    if best is None:
        raise RuntimeError("dense integer search found no candidate")

    return best


def dense_motion_residuals(
    frame: bytes,
    previous: bytes,
    w: int,
    h: int,
):
    cy, cu, cv = split_np(frame, w, h)
    py, pu, pv = split_np(previous, w, h)

    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2

    motion = bytearray(bh * bw)

    ry = np.empty_like(cy)
    floor_u = np.empty_like(cu)
    floor_v = np.empty_like(cv)
    trunc_u = np.empty_like(cu)
    trunc_v = np.empty_like(cv)

    odd_any = 0
    odd_x = 0
    odd_y = 0
    nonzero = 0
    manhattan_sum = 0
    luma_sad_sum = 0

    k = 0

    for by in range(bh):
        y0 = by * BLOCK

        for bx in range(bw):
            x0 = bx * BLOCK

            cost, index, dx, dy = _best_dense_luma(
                cy, py, x0, y0, w, h
            )

            motion[k] = index
            k += 1

            luma_sad_sum += cost
            manhattan_sum += abs(dx) + abs(dy)
            if dx != 0 or dy != 0:
                nonzero += 1
            if dx & 1:
                odd_x += 1
            if dy & 1:
                odd_y += 1
            if (dx & 1) or (dy & 1):
                odd_any += 1

            cur = cy[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)
            pred = py[
                y0 + dy:y0 + dy + BLOCK,
                x0 + dx:x0 + dx + BLOCK,
            ].astype(np.int16)
            ry[y0:y0 + BLOCK, x0:x0 + BLOCK] = (
                (cur - pred) & 255
            ).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2

            ucur = cu[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)
            vcur = cv[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)

            for policy, out_u, out_v in (
                (CHROMA_FLOOR, floor_u, floor_v),
                (CHROMA_TRUNC, trunc_u, trunc_v),
            ):
                cdx = chroma_shift(dx, policy)
                cdy = chroma_shift(dy, policy)

                upred = pu[
                    cy0 + cdy:cy0 + cdy + cb,
                    cx0 + cdx:cx0 + cdx + cb,
                ].astype(np.int16)
                vpred = pv[
                    cy0 + cdy:cy0 + cdy + cb,
                    cx0 + cdx:cx0 + cdx + cb,
                ].astype(np.int16)

                out_u[
                    cy0:cy0 + cb,
                    cx0:cx0 + cb,
                ] = ((ucur - upred) & 255).astype(np.uint8)
                out_v[
                    cy0:cy0 + cb,
                    cx0:cx0 + cb,
                ] = ((vcur - vpred) & 255).astype(np.uint8)

    total_blocks = bh * bw

    luma_bytes = ry.tobytes()
    residual_floor = (
        luma_bytes
        + floor_u.tobytes()
        + floor_v.tobytes()
    )
    residual_trunc = (
        luma_bytes
        + trunc_u.tobytes()
        + trunc_v.tobytes()
    )

    stats = {
        "total_blocks": total_blocks,
        "odd_any_blocks": odd_any,
        "odd_any_fraction": (
            odd_any / total_blocks if total_blocks else 0.0
        ),
        "odd_x_fraction": (
            odd_x / total_blocks if total_blocks else 0.0
        ),
        "odd_y_fraction": (
            odd_y / total_blocks if total_blocks else 0.0
        ),
        "nonzero_fraction": (
            nonzero / total_blocks if total_blocks else 0.0
        ),
        "mean_manhattan": (
            manhattan_sum / total_blocks if total_blocks else 0.0
        ),
        "mean_luma_sad": (
            luma_sad_sum / total_blocks if total_blocks else 0.0
        ),
    }

    return bytes(motion), {
        CHROMA_FLOOR: residual_floor,
        CHROMA_TRUNC: residual_trunc,
    }, stats


def dense_motion_inverse(
    motion: bytes,
    residual: bytes,
    previous: bytes,
    w: int,
    h: int,
    chroma_policy: int,
):
    py, pu, pv = split_np(previous, w, h)

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

    bh = h // BLOCK
    bw = w // BLOCK
    cb = BLOCK // 2

    if len(motion) != bh * bw:
        raise ValueError("bad KSV-17 motion map")

    oy = np.empty_like(py)
    ou = np.empty_like(pu)
    ov = np.empty_like(pv)

    k = 0

    for by in range(bh):
        y0 = by * BLOCK

        for bx in range(bw):
            x0 = bx * BLOCK
            index = motion[k]
            k += 1

            if index >= len(DENSE_CANDIDATES):
                raise ValueError("bad KSV-17 motion index")

            dx, dy = DENSE_CANDIDATES[index]
            sx = x0 + dx
            sy = y0 + dy

            if (
                sx < 0
                or sy < 0
                or sx + BLOCK > w
                or sy + BLOCK > h
            ):
                raise ValueError("KSV-17 luma vector out of bounds")

            pred = py[
                sy:sy + BLOCK,
                sx:sx + BLOCK,
            ].astype(np.int16)
            rr = ry[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)

            oy[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ] = ((pred + rr) & 255).astype(np.uint8)

            cx0 = x0 // 2
            cy0 = y0 // 2
            cdx = chroma_shift(dx, chroma_policy)
            cdy = chroma_shift(dy, chroma_policy)

            csx = cx0 + cdx
            csy = cy0 + cdy

            if (
                csx < 0
                or csy < 0
                or csx + cb > cw
                or csy + cb > ch
            ):
                raise ValueError("KSV-17 chroma vector out of bounds")

            upred = pu[
                csy:csy + cb,
                csx:csx + cb,
            ].astype(np.int16)
            vpred = pv[
                csy:csy + cb,
                csx:csx + cb,
            ].astype(np.int16)
            urr = ru[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)
            vrr = rv[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ].astype(np.int16)

            ou[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ] = ((upred + urr) & 255).astype(np.uint8)
            ov[
                cy0:cy0 + cb,
                cx0:cx0 + cb,
            ] = ((vpred + vrr) & 255).astype(np.uint8)

    return oy.tobytes() + ou.tobytes() + ov.tobytes()


def build_dense_records(
    raw_chunk: bytes,
    w: int,
    h: int,
    gop: int,
):
    fs = k13.frame_size(w, h)
    total = len(raw_chunk) // fs

    chunks = []
    frame_stats = []
    t0 = time.perf_counter()

    off = 0

    while off < total:
        n = min(gop, total - off)
        records = []
        previous = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]

            if previous is None:
                spatial = spatial_frame(frame, w, h)
                records.append(("I", spatial))
            else:
                motion, residuals, stats = dense_motion_residuals(
                    frame, previous, w, h
                )
                records.append((
                    "P",
                    motion,
                    residuals[CHROMA_FLOOR],
                    residuals[CHROMA_TRUNC],
                ))
                frame_stats.append(stats)

            previous = frame

        chunks.append((n, records))
        off += n

    return chunks, frame_stats, time.perf_counter() - t0


def serialize_dense(
    chunks,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    chroma_policy: int,
    residual_mode: int,
):
    if chroma_policy not in (CHROMA_FLOOR, CHROMA_TRUNC):
        raise ValueError("bad KSV-17 chroma policy")
    if residual_mode not in (DENSE_MOD8, DENSE_ZZ):
        raise ValueError("bad KSV-17 residual mode")

    out = bytearray()

    out.extend(DENSE_HDR.pack(
        DENSE_MAGIC,
        DENSE_VERSION,
        FMT_YUV420P8,
        gop,
        BLOCK,
        RADIUS,
        chroma_policy,
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
                continue

            _, motion, floor_residual, trunc_residual = rec
            residual = (
                floor_residual
                if chroma_policy == CHROMA_FLOOR
                else trunc_residual
            )

            payload.extend(motion)
            payload.extend(
                map_residual(residual, ZZ_INTER)
                if residual_mode == DENSE_ZZ
                else residual
            )

        p = bytes(payload)

        out.extend(DENSE_CHUNK.pack(
            n,
            len(p),
            zlib.crc32(p) & 0xFFFFFFFF,
        ))
        out.extend(p)

    return bytes(out)


def decode_dense_front(front: bytes) -> bytes:
    if len(front) < DENSE_HDR.size:
        raise ValueError("truncated KSV-17 header")

    (
        magic,
        version,
        fmt,
        gop,
        block,
        radius,
        chroma_policy,
        residual_mode,
        w,
        h,
        fpsn,
        fpsd,
    ) = DENSE_HDR.unpack_from(front, 0)

    if (
        magic != DENSE_MAGIC
        or version != DENSE_VERSION
        or fmt != FMT_YUV420P8
        or block != BLOCK
        or radius != RADIUS
        or chroma_policy not in (CHROMA_FLOOR, CHROMA_TRUNC)
        or residual_mode not in (DENSE_MOD8, DENSE_ZZ)
    ):
        raise ValueError("unsupported KSV-17 stream")

    del fpsn, fpsd

    fs = k13.frame_size(w, h)
    mvn = (w // BLOCK) * (h // BLOCK)

    pos = DENSE_HDR.size
    out = bytearray()

    while pos < len(front):
        if pos + DENSE_CHUNK.size > len(front):
            raise ValueError("truncated KSV-17 chunk header")

        n, size, crc = DENSE_CHUNK.unpack_from(front, pos)
        pos += DENSE_CHUNK.size

        if n < 1 or n > gop or pos + size > len(front):
            raise ValueError("bad KSV-17 chunk")

        payload = front[pos:pos + size]
        pos += size

        if zlib.crc32(payload) & 0xFFFFFFFF != crc:
            raise ValueError("KSV-17 CRC mismatch")

        q = 0
        previous = None

        for _ in range(n):
            if previous is None:
                if q + fs > len(payload):
                    raise ValueError("truncated KSV-17 intra")
                spatial = payload[q:q + fs]
                q += fs
                frame = spatial_frame_inv(spatial, w, h)
            else:
                if q + mvn + fs > len(payload):
                    raise ValueError("truncated KSV-17 inter")

                motion = payload[q:q + mvn]
                q += mvn

                mapped = payload[q:q + fs]
                q += fs

                residual = (
                    unmap_residual(mapped, ZZ_INTER)
                    if residual_mode == DENSE_ZZ
                    else mapped
                )

                frame = dense_motion_inverse(
                    motion,
                    residual,
                    previous,
                    w,
                    h,
                    chroma_policy,
                )

            out.extend(frame)
            previous = frame

        if q != len(payload):
            raise ValueError("KSV-17 trailing payload bytes")

    return bytes(out)


def dense_candidates_for_window(
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
    chunks, stats, search_seconds = build_dense_records(
        raw_chunk, w, h, gop
    )

    mean_odd_fraction = (
        sum(s["odd_any_fraction"] for s in stats) / len(stats)
        if stats else 0.0
    )
    max_odd_fraction = (
        max((s["odd_any_fraction"] for s in stats), default=0.0)
    )
    mean_manhattan = (
        sum(s["mean_manhattan"] for s in stats) / len(stats)
        if stats else 0.0
    )
    mean_luma_sad = (
        sum(s["mean_luma_sad"] for s in stats) / len(stats)
        if stats else 0.0
    )

    rows = []

    configs = (
        (
            CHROMA_FLOOR,
            DENSE_MOD8,
            "DENSE_FLOOR_MOD8",
            MODE_DENSE_FLOOR_MOD8,
        ),
        (
            CHROMA_FLOOR,
            DENSE_ZZ,
            "DENSE_FLOOR_ZZ",
            MODE_DENSE_FLOOR_ZZ,
        ),
        (
            CHROMA_TRUNC,
            DENSE_MOD8,
            "DENSE_TRUNC_MOD8",
            MODE_DENSE_TRUNC_MOD8,
        ),
        (
            CHROMA_TRUNC,
            DENSE_ZZ,
            "DENSE_TRUNC_ZZ",
            MODE_DENSE_TRUNC_ZZ,
        ),
    )

    for chroma_policy, residual_mode, label, outer_mode in configs:
        t0 = time.perf_counter()
        front = serialize_dense(
            chunks,
            w,
            h,
            fpsn,
            fpsd,
            gop,
            chroma_policy,
            residual_mode,
        )
        serialization_seconds = time.perf_counter() - t0

        payload, backend_seconds = k13.compress_bytes(
            front,
            exe,
            tmp,
            f"{tag}.{label.lower()}",
        )

        rows.append({
            "mode": outer_mode,
            "label": label,
            "payload": payload,
            "frontend_seconds": (
                search_seconds + serialization_seconds
            ),
            "backend_seconds": backend_seconds,
            "search_seconds": search_seconds,
            "mean_odd_fraction": mean_odd_fraction,
            "max_odd_fraction": max_odd_fraction,
            "mean_manhattan": mean_manhattan,
            "mean_luma_sad": mean_luma_sad,
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
        raw_chunk,
        exe,
        tmp,
        w,
        h,
        fpsn,
        fpsd,
        gop,
        tag,
    )

    sparse, sparse_search_seconds = k13.radius_candidates(
        raw_chunk,
        exe,
        tmp,
        w,
        h,
        fpsn,
        fpsd,
        gop,
        k13.R4,
        tag,
    )

    temp = dict(temp)
    temp["mode"] = MODE_TEMP
    temp["label"] = "TEMP"

    sparse_mod8 = dict(sparse[0])
    sparse_mod8["mode"] = MODE_R4_MOD8
    sparse_mod8["label"] = "MC_R4_MOD8"

    sparse_zz = dict(sparse[1])
    sparse_zz["mode"] = MODE_R4_ZZ
    sparse_zz["label"] = "MC_R4_ZZ"

    return temp, [sparse_mod8, sparse_zz], sparse_search_seconds


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
        raise ValueError("truncated KSV-17 outer header")

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
        raise ValueError("bad KSV-17 outer stream")

    del fpsn, fpsd, gop, route_span

    pos = OUTER_HDR.size
    out = bytearray()

    with tempfile.TemporaryDirectory(prefix="ksv17_dec_") as td:
        tmp = Path(td)
        index = 0

        while pos < len(data):
            if pos + OUTER_ENT.size > len(data):
                raise ValueError("truncated KSV-17 outer entry")

            mode, frames, payload_size = OUTER_ENT.unpack_from(data, pos)
            pos += OUTER_ENT.size

            if pos + payload_size > len(data):
                raise ValueError("truncated KSV-17 outer payload")

            payload = data[pos:pos + payload_size]
            pos += payload_size

            arc = tmp / f"{index}.aur"
            outdir = tmp / f"{index}.out"
            front = tmp / f"{index}.front"
            raw = tmp / f"{index}.yuv"

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
            elif mode in (
                MODE_DENSE_FLOOR_MOD8,
                MODE_DENSE_FLOOR_ZZ,
                MODE_DENSE_TRUNC_MOD8,
                MODE_DENSE_TRUNC_ZZ,
            ):
                chunk = decode_dense_front(front.read_bytes())
            else:
                raise ValueError("unknown KSV-17 outer mode")

            if len(chunk) != frames * k13.frame_size(w, h):
                raise ValueError("KSV-17 decoded frame count mismatch")

            out.extend(chunk)
            index += 1

    dst.write_bytes(out)


def policy_stats(entries):
    return dict(sorted(Counter(e["label"] for e in entries).items()))


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
    dense_entries = []
    oracle_entries = []
    windows = []

    baseline_research_seconds = 0.0
    dense_research_seconds = 0.0
    oracle_research_seconds = 0.0

    with tempfile.TemporaryDirectory(prefix="ksv17_enc_") as td:
        tmp = Path(td)

        for window_index, off in enumerate(
            range(0, total, route_span)
        ):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, sparse, sparse_search_seconds = baseline_candidates(
                chunk,
                exe,
                tmp,
                w,
                h,
                fpsn,
                fpsd,
                gop,
                f"w{window_index}",
            )

            dense, dense_search_seconds = dense_candidates_for_window(
                chunk,
                exe,
                tmp,
                w,
                h,
                fpsn,
                fpsd,
                gop,
                f"w{window_index}",
            )

            baseline = choose([temp, *sparse])
            dense_policy = choose([temp, *dense])
            oracle = choose([temp, *sparse, *dense])

            for entry in (baseline, dense_policy, oracle):
                entry["frames"] = n

            baseline_entries.append(dict(baseline))
            dense_entries.append(dict(dense_policy))
            oracle_entries.append(dict(oracle))

            temp_cost = (
                temp["frontend_seconds"]
                + temp["backend_seconds"]
            )
            sparse_cost = (
                sparse_search_seconds
                + sum(x["backend_seconds"] for x in sparse)
            )
            dense_cost = (
                dense_search_seconds
                + sum(x["backend_seconds"] for x in dense)
            )

            baseline_research_seconds += temp_cost + sparse_cost
            dense_research_seconds += temp_cost + dense_cost
            oracle_research_seconds += (
                temp_cost + sparse_cost + dense_cost
            )

            best_dense = choose(dense)

            windows.append({
                "window": window_index,
                "frames": n,
                "temp_bytes": len(temp["payload"]),
                "sparse_mod8_bytes": len(sparse[0]["payload"]),
                "sparse_zz_bytes": len(sparse[1]["payload"]),
                "best_dense_label": best_dense["label"],
                "best_dense_bytes": len(best_dense["payload"]),
                "dense_search_seconds": best_dense["search_seconds"],
                "dense_mean_odd_fraction": best_dense[
                    "mean_odd_fraction"
                ],
                "dense_max_odd_fraction": best_dense[
                    "max_odd_fraction"
                ],
                "dense_mean_manhattan": best_dense[
                    "mean_manhattan"
                ],
                "dense_mean_luma_sad": best_dense[
                    "mean_luma_sad"
                ],
                "baseline_selected": baseline["label"],
                "dense_selected": dense_policy["label"],
                "oracle_selected": oracle["label"],
            })

    paths = {
        "baseline": prefix.with_suffix(".baseline.k17"),
        "dense": prefix.with_suffix(".dense.k17"),
        "oracle": prefix.with_suffix(".oracle.k17"),
    }

    write_outer(
        paths["baseline"],
        w,
        h,
        fpsn,
        fpsd,
        gop,
        route_span,
        baseline_entries,
    )

    write_outer(
        paths["dense"],
        w,
        h,
        fpsn,
        fpsd,
        gop,
        route_span,
        dense_entries,
    )

    write_outer(
        paths["oracle"],
        w,
        h,
        fpsn,
        fpsd,
        gop,
        route_span,
        oracle_entries,
    )

    return {
        "paths": paths,
        "baseline": {
            "bytes": paths["baseline"].stat().st_size,
            "encode_research_seconds": baseline_research_seconds,
            "modes": policy_stats(baseline_entries),
        },
        "dense": {
            "bytes": paths["dense"].stat().st_size,
            "encode_research_seconds": dense_research_seconds,
            "modes": policy_stats(dense_entries),
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
    ap.add_argument(
        "--clip",
        action="append",
        type=parse_clip,
        required=True,
    )
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

        for policy in ("baseline", "dense", "oracle"):
            dst = OUT / f"{clip['name']}.{policy}.decoded.yuv"

            t0 = time.perf_counter()
            decode_outer(
                encoded["paths"][policy],
                dst,
                args.kephir,
            )
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
            "dense": {
                **encoded["dense"],
                **decoded["dense"],
            },
            "oracle": {
                **encoded["oracle"],
                **decoded["oracle"],
            },
            "windows": encoded["windows"],
        }

        for policy in ("baseline", "dense", "oracle"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        row["dense_delta_bytes"] = (
            row["dense"]["bytes"]
            - row["baseline"]["bytes"]
        )
        row["dense_delta_percent"] = (
            100.0 * (
                row["dense"]["bytes"]
                / row["baseline"]["bytes"]
                - 1.0
            )
        )
        row["oracle_delta_bytes"] = (
            row["oracle"]["bytes"]
            - row["baseline"]["bytes"]
        )
        row["oracle_delta_percent"] = (
            100.0 * (
                row["oracle"]["bytes"]
                / row["baseline"]["bytes"]
                - 1.0
            )
        )

        rows.append(row)

        print(
            "KSV17_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "dense", row["dense"]["bytes"],
            "oracle", row["oracle"]["bytes"],
            "dense_delta_pct",
            f"{row['dense_delta_percent']:.6f}",
            "oracle_delta_pct",
            f"{row['oracle_delta_percent']:.6f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)

    aggregate = {}

    for policy in ("baseline", "dense", "oracle"):
        total = sum(r[policy]["bytes"] for r in rows)

        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": (
                100.0 * total / raw_total
            ),
            "encode_research_seconds": sum(
                r[policy]["encode_research_seconds"]
                for r in rows
            ),
        }

    aggregate["dense_delta_bytes"] = (
        aggregate["dense"]["bytes"]
        - aggregate["baseline"]["bytes"]
    )
    aggregate["dense_delta_percent"] = (
        100.0 * (
            aggregate["dense"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )
    aggregate["oracle_delta_bytes"] = (
        aggregate["oracle"]["bytes"]
        - aggregate["baseline"]["bytes"]
    )
    aggregate["oracle_delta_percent"] = (
        100.0 * (
            aggregate["oracle"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )

    result = {
        "experiment": "KSV-17 dense integer motion",
        "block": BLOCK,
        "radius": RADIUS,
        "sparse_candidate_count": 25,
        "dense_candidate_count": len(DENSE_CANDIDATES),
        "dense_chroma_policies": {
            "floor": "d//2",
            "trunc": "int(d/2)",
        },
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "Dense luma motion evaluates every integer dx/dy in [-4,+4].",
            "The motion map remains one byte per 8x8 block.",
            "FLOOR and TRUNC chroma policies share the same dense luma search.",
            "Baseline matches the KSV-13 TEMP/sparse-R4 candidate set.",
            "Oracle compares baseline plus every dense candidate.",
            "Every emitted stream is independently decoded and SHA verified.",
            "Research encode time includes duplicate candidate encodes and is not production throughput.",
        ],
    }

    (OUT / "KSV17_RESULTS.json").write_text(
        json.dumps(result, indent=2)
    )

    print("KSV17_DENSE_INTEGER_PASS")
    print(
        "KSV17_AGGREGATE",
        "baseline", aggregate["baseline"]["bytes"],
        "dense", aggregate["dense"]["bytes"],
        "oracle", aggregate["oracle"]["bytes"],
        "dense_delta_pct",
        f"{aggregate['dense_delta_percent']:.6f}",
        "oracle_delta_pct",
        f"{aggregate['oracle_delta_percent']:.6f}",
    )


if __name__ == "__main__":
    main()
