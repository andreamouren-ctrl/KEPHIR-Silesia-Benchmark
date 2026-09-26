#!/usr/bin/env python3
"""
KSV-16 Block Hybrid Inter/Intra Prediction.

Research goal:
stop forcing temporal prediction on blocks where local spatial prediction is
better. This directly targets occlusion, newly revealed regions, texture and
non-coherent high motion.

Per 8x8 luma block:
- codes 0..24: existing MC8R4 inter candidate
- code 25: block-local horizontal intra predictor
- code 26: block-local vertical intra predictor

Chroma follows the selected luma-block mode using 4x4 blocks.

Three intra-selection penalties are tested (0, 128, 512) together with both
MOD8 and ZZ_INTER residual mappings. Final candidate choice is based on KHEPRI
EXP-40 bytes, not frontend size.

Policies:
- baseline: TEMP / MC8R4 MOD8 / MC8R4 ZZ
- hybrid: baseline + all hybrid candidates
- hybrid_only: TEMP + all hybrid candidates

Every emitted stream is independently decoded and SHA verified.
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
    motion_residual,
    decode_file as mc_decode,
)
from kstream_video_residual_symbols_v7 import (
    ZZ_INTER,
    map_residual,
    unmap_residual,
    decode_file as zz_decode,
)

OUT = Path("results/video/ksv16_block_hybrid")

BLOCK = 8
CHROMA_BLOCK = 4
RADIUS = 4
INTRA_H = 25
INTRA_V = 26
PENALTIES = (0, 128, 512)

FMT_YUV420P8 = 1

HYB_MAGIC = b"K16H"
HYB_VERSION = 1
HYB_MOD8 = 0
HYB_ZZ = 1
HYB_HDR = struct.Struct("<4sBBBBBBHHII")
HYB_CHUNK = struct.Struct("<III")

OUTER_MAGIC = b"K16O"
OUTER_VERSION = 1
OUTER_HDR = struct.Struct("<4sBHHIIII")
OUTER_ENT = struct.Struct("<BII")

MODE_TEMP = 0
MODE_R4_MOD8 = 1
MODE_R4_ZZ = 2
MODE_HYB_MOD8 = 3
MODE_HYB_ZZ = 4

MAG_LUT = np.array([min(i, 256 - i) for i in range(256)], dtype=np.uint16)


def split_np(frame: bytes, w: int, h: int):
    y, u, v, cw, ch = split_frame(frame, w, h)
    return (
        np.frombuffer(y, dtype=np.uint8).reshape(h, w),
        np.frombuffer(u, dtype=np.uint8).reshape(ch, cw),
        np.frombuffer(v, dtype=np.uint8).reshape(ch, cw),
    )


def horizontal_residual_plane(src: np.ndarray, block: int):
    s = src.astype(np.int16)
    out = np.empty_like(src)
    out[:, 0] = src[:, 0]
    out[:, 1:] = ((s[:, 1:] - s[:, :-1]) & 255).astype(np.uint8)
    # Restart the predictor at each block boundary.
    out[:, ::block] = src[:, ::block]
    return out


def vertical_residual_plane(src: np.ndarray, block: int):
    s = src.astype(np.int16)
    out = np.empty_like(src)
    out[0, :] = src[0, :]
    out[1:, :] = ((s[1:, :] - s[:-1, :]) & 255).astype(np.uint8)
    # Restart the predictor at each block boundary.
    out[::block, :] = src[::block, :]
    return out


def inverse_horizontal_block(res: np.ndarray):
    return (np.cumsum(res.astype(np.uint16), axis=1) & 255).astype(np.uint8)


def inverse_vertical_block(res: np.ndarray):
    return (np.cumsum(res.astype(np.uint16), axis=0) & 255).astype(np.uint8)


def residual_block_metric(
    y: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    w: int,
    h: int,
):
    bh = h // BLOCK
    bw = w // BLOCK

    ym = MAG_LUT[y].reshape(bh, BLOCK, bw, BLOCK).sum(axis=(1, 3))
    um = MAG_LUT[u].reshape(
        bh, CHROMA_BLOCK, bw, CHROMA_BLOCK
    ).sum(axis=(1, 3))
    vm = MAG_LUT[v].reshape(
        bh, CHROMA_BLOCK, bw, CHROMA_BLOCK
    ).sum(axis=(1, 3))
    return ym + um + vm


def residual_blocks_view_y(a: np.ndarray, h: int, w: int):
    bh = h // BLOCK
    bw = w // BLOCK
    return a.reshape(bh, BLOCK, bw, BLOCK).transpose(0, 2, 1, 3)


def residual_blocks_view_c(a: np.ndarray, h: int, w: int):
    bh = h // BLOCK
    bw = w // BLOCK
    return a.reshape(
        bh, CHROMA_BLOCK, bw, CHROMA_BLOCK
    ).transpose(0, 2, 1, 3)


def blocks_to_plane_y(b: np.ndarray):
    bh, bw, _, _ = b.shape
    return b.transpose(0, 2, 1, 3).reshape(bh * BLOCK, bw * BLOCK)


def blocks_to_plane_c(b: np.ndarray):
    bh, bw, _, _ = b.shape
    return b.transpose(0, 2, 1, 3).reshape(
        bh * CHROMA_BLOCK, bw * CHROMA_BLOCK
    )


def precompute_frame_fields(frame: bytes, prev: bytes, w: int, h: int):
    motion_map, motion_residual_bytes = motion_residual(
        frame, prev, w, h, BLOCK, RADIUS
    )

    cy, cu, cv = split_np(frame, w, h)
    my, mu, mv = split_np(motion_residual_bytes, w, h)

    hy = horizontal_residual_plane(cy, BLOCK)
    hu = horizontal_residual_plane(cu, CHROMA_BLOCK)
    hv = horizontal_residual_plane(cv, CHROMA_BLOCK)

    vy = vertical_residual_plane(cy, BLOCK)
    vu = vertical_residual_plane(cu, CHROMA_BLOCK)
    vv = vertical_residual_plane(cv, CHROMA_BLOCK)

    mm = residual_block_metric(my, mu, mv, w, h)
    hm = residual_block_metric(hy, hu, hv, w, h)
    vm = residual_block_metric(vy, vu, vv, w, h)

    return {
        "motion_map": np.frombuffer(motion_map, dtype=np.uint8).reshape(
            h // BLOCK, w // BLOCK
        ),
        "motion_y": my,
        "motion_u": mu,
        "motion_v": mv,
        "h_y": hy,
        "h_u": hu,
        "h_v": hv,
        "v_y": vy,
        "v_u": vu,
        "v_v": vv,
        "motion_metric": mm,
        "h_metric": hm,
        "v_metric": vm,
    }


def build_hybrid_frame(fields, w: int, h: int, penalty: int):
    motion_metric = fields["motion_metric"]
    h_metric = fields["h_metric"]
    v_metric = fields["v_metric"]

    h_better = h_metric <= v_metric
    intra_metric = np.minimum(h_metric, v_metric)
    use_intra = (intra_metric.astype(np.uint64) + penalty) < motion_metric

    mode = fields["motion_map"].copy()
    mode[use_intra & h_better] = INTRA_H
    mode[use_intra & ~h_better] = INTRA_V

    oy = residual_blocks_view_y(fields["motion_y"], h, w).copy()
    ou = residual_blocks_view_c(fields["motion_u"], h, w).copy()
    ov = residual_blocks_view_c(fields["motion_v"], h, w).copy()

    hy = residual_blocks_view_y(fields["h_y"], h, w)
    hu = residual_blocks_view_c(fields["h_u"], h, w)
    hv = residual_blocks_view_c(fields["h_v"], h, w)

    vy = residual_blocks_view_y(fields["v_y"], h, w)
    vu = residual_blocks_view_c(fields["v_u"], h, w)
    vv = residual_blocks_view_c(fields["v_v"], h, w)

    mask_h = use_intra & h_better
    mask_v = use_intra & ~h_better

    oy[mask_h] = hy[mask_h]
    ou[mask_h] = hu[mask_h]
    ov[mask_h] = hv[mask_h]

    oy[mask_v] = vy[mask_v]
    ou[mask_v] = vu[mask_v]
    ov[mask_v] = vv[mask_v]

    residual = (
        blocks_to_plane_y(oy).tobytes()
        + blocks_to_plane_c(ou).tobytes()
        + blocks_to_plane_c(ov).tobytes()
    )

    total = mode.size
    intra_h = int(mask_h.sum())
    intra_v = int(mask_v.sum())

    stats = {
        "penalty": penalty,
        "intra_h_blocks": intra_h,
        "intra_v_blocks": intra_v,
        "intra_fraction": (
            (intra_h + intra_v) / total if total else 0.0
        ),
        "mean_motion_metric": float(motion_metric.mean()),
        "mean_best_intra_metric": float(intra_metric.mean()),
    }
    return mode.astype(np.uint8).tobytes(), residual, stats


def hybrid_inverse(
    mode_map: bytes,
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

    cand = local_candidates(RADIUS)
    bh = h // BLOCK
    bw = w // BLOCK
    if len(mode_map) != bh * bw:
        raise ValueError("bad KSV-16 mode map")

    mode = np.frombuffer(mode_map, dtype=np.uint8).reshape(bh, bw)
    oy = np.empty_like(py)
    ou = np.empty_like(pu)
    ov = np.empty_like(pv)

    for by in range(bh):
        y0 = by * BLOCK
        cy0 = by * CHROMA_BLOCK

        for bx in range(bw):
            x0 = bx * BLOCK
            cx0 = bx * CHROMA_BLOCK
            code = int(mode[by, bx])

            if code < len(cand):
                dx, dy = cand[code]
                sx = x0 + dx
                sy = y0 + dy
                if (
                    sx < 0 or sy < 0
                    or sx + BLOCK > w
                    or sy + BLOCK > h
                ):
                    raise ValueError("KSV-16 motion vector out of bounds")

                pred = py[
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

                cdx = dx // 2
                cdy = dy // 2

                upred = pu[
                    cy0 + cdy:cy0 + cdy + CHROMA_BLOCK,
                    cx0 + cdx:cx0 + cdx + CHROMA_BLOCK,
                ].astype(np.int16)
                vpred = pv[
                    cy0 + cdy:cy0 + cdy + CHROMA_BLOCK,
                    cx0 + cdx:cx0 + cdx + CHROMA_BLOCK,
                ].astype(np.int16)

                urr = ru[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ].astype(np.int16)
                vrr = rv[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ].astype(np.int16)

                ou[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ] = ((upred + urr) & 255).astype(np.uint8)
                ov[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ] = ((vpred + vrr) & 255).astype(np.uint8)

            elif code in (INTRA_H, INTRA_V):
                yres = ry[y0:y0 + BLOCK, x0:x0 + BLOCK]
                ures = ru[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ]
                vres = rv[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ]

                inv = (
                    inverse_horizontal_block
                    if code == INTRA_H
                    else inverse_vertical_block
                )
                oy[y0:y0 + BLOCK, x0:x0 + BLOCK] = inv(yres)
                ou[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ] = inv(ures)
                ov[
                    cy0:cy0 + CHROMA_BLOCK,
                    cx0:cx0 + CHROMA_BLOCK,
                ] = inv(vres)
            else:
                raise ValueError("unknown KSV-16 block mode")

    return oy.tobytes() + ou.tobytes() + ov.tobytes()


def build_hybrid_records(
    raw_chunk: bytes,
    w: int,
    h: int,
    gop: int,
    penalty: int,
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
        prev = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]

            if prev is None:
                records.append(("I", spatial_frame(frame, w, h)))
            else:
                fields = precompute_frame_fields(frame, prev, w, h)
                mode_map, residual, stats = build_hybrid_frame(
                    fields, w, h, penalty
                )
                records.append(("P", mode_map, residual))
                frame_stats.append(stats)

            prev = frame

        chunks.append((n, records))
        off += n

    return chunks, frame_stats, time.perf_counter() - t0


def build_hybrid_records_multi(
    raw_chunk: bytes,
    w: int,
    h: int,
    gop: int,
    penalties,
):
    fs = k13.frame_size(w, h)
    total = len(raw_chunk) // fs
    chunks_by_penalty = {p: [] for p in penalties}
    stats_by_penalty = {p: [] for p in penalties}

    t0 = time.perf_counter()
    off = 0

    while off < total:
        n = min(gop, total - off)
        records = {p: [] for p in penalties}
        prev = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]

            if prev is None:
                spatial = spatial_frame(frame, w, h)
                for p in penalties:
                    records[p].append(("I", spatial))
            else:
                fields = precompute_frame_fields(frame, prev, w, h)
                for p in penalties:
                    mode_map, residual, stats = build_hybrid_frame(
                        fields, w, h, p
                    )
                    records[p].append(("P", mode_map, residual))
                    stats_by_penalty[p].append(stats)

            prev = frame

        for p in penalties:
            chunks_by_penalty[p].append((n, records[p]))
        off += n

    return (
        chunks_by_penalty,
        stats_by_penalty,
        time.perf_counter() - t0,
    )


def serialize_hybrid(
    chunks,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    residual_mode: int,
):
    if residual_mode not in (HYB_MOD8, HYB_ZZ):
        raise ValueError("bad KSV-16 residual mode")

    out = bytearray()
    out.extend(HYB_HDR.pack(
        HYB_MAGIC,
        HYB_VERSION,
        FMT_YUV420P8,
        gop,
        BLOCK,
        RADIUS,
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
                _, mode_map, residual = rec
                payload.extend(mode_map)
                payload.extend(
                    map_residual(residual, ZZ_INTER)
                    if residual_mode == HYB_ZZ
                    else residual
                )

        p = bytes(payload)
        out.extend(HYB_CHUNK.pack(
            n, len(p), zlib.crc32(p) & 0xFFFFFFFF
        ))
        out.extend(p)

    return bytes(out)


def decode_hybrid_front(front: bytes) -> bytes:
    if len(front) < HYB_HDR.size:
        raise ValueError("truncated KSV-16 header")

    (
        magic,
        version,
        fmt,
        gop,
        block,
        radius,
        residual_mode,
        w,
        h,
        fpsn,
        fpsd,
    ) = HYB_HDR.unpack_from(front, 0)

    if (
        magic != HYB_MAGIC
        or version != HYB_VERSION
        or fmt != FMT_YUV420P8
        or block != BLOCK
        or radius != RADIUS
        or residual_mode not in (HYB_MOD8, HYB_ZZ)
    ):
        raise ValueError("unsupported KSV-16 stream")

    del fpsn, fpsd

    fs = k13.frame_size(w, h)
    mvn = (w // BLOCK) * (h // BLOCK)

    pos = HYB_HDR.size
    out = bytearray()

    while pos < len(front):
        if pos + HYB_CHUNK.size > len(front):
            raise ValueError("truncated KSV-16 chunk header")

        n, size, crc = HYB_CHUNK.unpack_from(front, pos)
        pos += HYB_CHUNK.size

        if n < 1 or n > gop or pos + size > len(front):
            raise ValueError("bad KSV-16 chunk")

        payload = front[pos:pos + size]
        pos += size

        if zlib.crc32(payload) & 0xFFFFFFFF != crc:
            raise ValueError("KSV-16 CRC mismatch")

        q = 0
        prev = None

        for _ in range(n):
            if prev is None:
                if q + fs > len(payload):
                    raise ValueError("truncated KSV-16 intra frame")
                spatial = payload[q:q + fs]
                q += fs
                frame = spatial_frame_inv(spatial, w, h)
            else:
                if q + mvn + fs > len(payload):
                    raise ValueError("truncated KSV-16 inter frame")
                mode_map = payload[q:q + mvn]
                q += mvn
                mapped = payload[q:q + fs]
                q += fs

                residual = (
                    unmap_residual(mapped, ZZ_INTER)
                    if residual_mode == HYB_ZZ
                    else mapped
                )
                frame = hybrid_inverse(
                    mode_map, residual, prev, w, h
                )

            out.extend(frame)
            prev = frame

        if q != len(payload):
            raise ValueError("KSV-16 trailing payload bytes")

    return bytes(out)


def hybrid_candidates(
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
    rows = []
    chunks_by_penalty, stats_by_penalty, shared_frontend_seconds = (
        build_hybrid_records_multi(
            raw_chunk, w, h, gop, PENALTIES
        )
    )

    for penalty in PENALTIES:
        chunks = chunks_by_penalty[penalty]
        stats = stats_by_penalty[penalty]

        mean_intra_fraction = (
            sum(s["intra_fraction"] for s in stats) / len(stats)
            if stats else 0.0
        )

        for residual_mode, suffix, outer_mode in (
            (HYB_MOD8, "MOD8", MODE_HYB_MOD8),
            (HYB_ZZ, "ZZ", MODE_HYB_ZZ),
        ):
            t0 = time.perf_counter()
            front = serialize_hybrid(
                chunks, w, h, fpsn, fpsd, gop, residual_mode
            )
            serialization_seconds = time.perf_counter() - t0
            payload, backend_seconds = k13.compress_bytes(
                front, exe, tmp,
                f"{tag}.p{penalty}.{suffix.lower()}",
            )

            rows.append({
                "mode": outer_mode,
                "label": f"HYB_P{penalty}_{suffix}",
                "payload": payload,
                "penalty": penalty,
                "frontend_seconds": (
                    shared_frontend_seconds + serialization_seconds
                ),
                "backend_seconds": backend_seconds,
                "mean_intra_fraction": mean_intra_fraction,
            })

    return rows


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
    r4, _ = k13.radius_candidates(
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

    return temp, [r4_mod, r4_zz]


def choose(candidates):
    return min(
        candidates,
        key=lambda x: (
            len(x["payload"]),
            x["mode"],
            x.get("penalty", -1),
        )
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
        raise ValueError("truncated KSV-16 outer header")

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
        raise ValueError("bad KSV-16 outer stream")

    del fpsn, fpsd, gop, route_span

    pos = OUTER_HDR.size
    out = bytearray()

    with tempfile.TemporaryDirectory(prefix="ksv16_dec_") as td:
        tmp = Path(td)
        idx = 0

        while pos < len(data):
            if pos + OUTER_ENT.size > len(data):
                raise ValueError("truncated KSV-16 outer entry")

            mode, frames, payload_size = OUTER_ENT.unpack_from(data, pos)
            pos += OUTER_ENT.size

            if pos + payload_size > len(data):
                raise ValueError("truncated KSV-16 outer payload")

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
            elif mode in (MODE_HYB_MOD8, MODE_HYB_ZZ):
                chunk = decode_hybrid_front(front.read_bytes())
            else:
                raise ValueError("unknown KSV-16 outer mode")

            if len(chunk) != frames * k13.frame_size(w, h):
                raise ValueError("KSV-16 decoded frame count mismatch")

            out.extend(chunk)
            idx += 1

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
    hybrid_entries = []
    hybrid_only_entries = []
    windows = []

    with tempfile.TemporaryDirectory(prefix="ksv16_enc_") as td:
        tmp = Path(td)

        for gi, off in enumerate(range(0, total, route_span)):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, r4 = baseline_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )
            hybrids = hybrid_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )

            baseline = choose([temp, *r4])
            hybrid = choose([temp, *r4, *hybrids])
            hybrid_only = choose([temp, *hybrids])

            for e in (baseline, hybrid, hybrid_only):
                e["frames"] = n

            baseline_entries.append(dict(baseline))
            hybrid_entries.append(dict(hybrid))
            hybrid_only_entries.append(dict(hybrid_only))

            best_hybrid = choose(hybrids)
            windows.append({
                "window": gi,
                "frames": n,
                "temp_bytes": len(temp["payload"]),
                "r4_mod8_bytes": len(r4[0]["payload"]),
                "r4_zz_bytes": len(r4[1]["payload"]),
                "best_hybrid_label": best_hybrid["label"],
                "best_hybrid_bytes": len(best_hybrid["payload"]),
                "best_hybrid_intra_fraction": best_hybrid[
                    "mean_intra_fraction"
                ],
                "baseline_selected": baseline["label"],
                "hybrid_selected": hybrid["label"],
                "hybrid_only_selected": hybrid_only["label"],
            })

    paths = {
        "baseline": prefix.with_suffix(".baseline.k16"),
        "hybrid": prefix.with_suffix(".hybrid.k16"),
        "hybrid_only": prefix.with_suffix(".hybrid_only.k16"),
    }

    write_outer(
        paths["baseline"],
        w, h, fpsn, fpsd, gop, route_span,
        baseline_entries,
    )
    write_outer(
        paths["hybrid"],
        w, h, fpsn, fpsd, gop, route_span,
        hybrid_entries,
    )
    write_outer(
        paths["hybrid_only"],
        w, h, fpsn, fpsd, gop, route_span,
        hybrid_only_entries,
    )

    return {
        "paths": paths,
        "baseline": {
            "bytes": paths["baseline"].stat().st_size,
            "modes": policy_stats(baseline_entries),
        },
        "hybrid": {
            "bytes": paths["hybrid"].stat().st_size,
            "modes": policy_stats(hybrid_entries),
        },
        "hybrid_only": {
            "bytes": paths["hybrid_only"].stat().st_size,
            "modes": policy_stats(hybrid_only_entries),
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
        for policy in ("baseline", "hybrid", "hybrid_only"):
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
            "hybrid": {
                **encoded["hybrid"],
                **decoded["hybrid"],
            },
            "hybrid_only": {
                **encoded["hybrid_only"],
                **decoded["hybrid_only"],
            },
            "windows": encoded["windows"],
        }

        for policy in ("baseline", "hybrid", "hybrid_only"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        row["hybrid_delta_bytes"] = (
            row["hybrid"]["bytes"] - row["baseline"]["bytes"]
        )
        row["hybrid_delta_percent"] = (
            100.0 * (
                row["hybrid"]["bytes"] / row["baseline"]["bytes"] - 1.0
            )
        )

        rows.append(row)

        print(
            "KSV16_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "hybrid", row["hybrid"]["bytes"],
            "hybrid_only", row["hybrid_only"]["bytes"],
            "hybrid_delta_pct", f"{row['hybrid_delta_percent']:.6f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)
    aggregate = {}

    for policy in ("baseline", "hybrid", "hybrid_only"):
        total = sum(r[policy]["bytes"] for r in rows)
        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": 100.0 * total / raw_total,
        }

    aggregate["hybrid_delta_bytes"] = (
        aggregate["hybrid"]["bytes"]
        - aggregate["baseline"]["bytes"]
    )
    aggregate["hybrid_delta_percent"] = (
        100.0 * (
            aggregate["hybrid"]["bytes"]
            / aggregate["baseline"]["bytes"]
            - 1.0
        )
    )

    result = {
        "experiment": "KSV-16 block hybrid inter/intra",
        "block": BLOCK,
        "radius": RADIUS,
        "penalties": list(PENALTIES),
        "block_modes": {
            "0..24": "MC8R4 inter",
            "25": "block-horizontal intra",
            "26": "block-vertical intra",
        },
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "Horizontal/vertical predictors reset at every luma/chroma block boundary.",
            "Intra selection uses signed residual magnitude plus a penalty.",
            "Final window candidate selection uses KHEPRI EXP-40 bytes.",
            "Hybrid policy includes the baseline candidates, so it cannot regress by construction.",
            "Every emitted stream is independently decoded and SHA verified.",
        ],
    }

    (OUT / "KSV16_RESULTS.json").write_text(json.dumps(result, indent=2))

    print("KSV16_BLOCK_HYBRID_PASS")
    print(
        "KSV16_AGGREGATE",
        "baseline", aggregate["baseline"]["bytes"],
        "hybrid", aggregate["hybrid"]["bytes"],
        "hybrid_only", aggregate["hybrid_only"]["bytes"],
        "hybrid_delta_pct", f"{aggregate['hybrid_delta_percent']:.6f}",
    )


if __name__ == "__main__":
    main()
