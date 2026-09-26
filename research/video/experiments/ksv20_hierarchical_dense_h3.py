#!/usr/bin/env python3
"""
KSV-20 H3 — Hierarchical Dense Integer Motion.

Goal:
recover most of KSV-17's dense integer compression gain without evaluating
all 81 motion vectors for every 8x8 block.

H3 search:
1. evaluate the existing 25 sparse-even MC8R4 candidates;
2. take the three best sparse vectors;
3. evaluate the unique 3x3 integer neighborhood around that vector;
4. choose the best evaluated vector using the same dense candidate tie order.

The emitted motion map uses the exact KSV-17 dense 0..80 candidate indexing,
so KSV-20 H3 reuses the K17D wire format and decoder unchanged.

Policies emitted:
- baseline: TEMP / sparse MC8R4 MOD8 / sparse MC8R4 ZZ;
- h3: TEMP / H3 FLOOR+TRUNC, each MOD8+ZZ;
- dense: TEMP / exhaustive KSV-17 FLOOR+TRUNC, each MOD8+ZZ.

All emitted streams are decoded and SHA verified.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

import ksv13_natural_radius_sweep as k13
import ksv17_dense_integer_motion as k17
from kstream_video_baseline import decode_file as temp_decode
from kstream_video_motion_control import (
    candidates as sparse_candidates,
    frame_sizes,
    spatial_frame,
)
from kstream_video_residual_symbols_v7 import (
    ZZ_INTER,
    map_residual,
    decode_file as zz_decode,
)
from kstream_video_motion_control import decode_file as mc_decode

OUT = Path("results/video/ksv20_hierarchical_dense_h3")

BLOCK = 8
RADIUS = 4
SPARSE = sparse_candidates(RADIUS)
DENSE = k17.DENSE_CANDIDATES
DENSE_INDEX = {v: i for i, v in enumerate(DENSE)}

MODE_TEMP = 0
MODE_R4_MOD8 = 1
MODE_R4_ZZ = 2
MODE_H3_FLOOR_MOD8 = 3
MODE_H3_FLOOR_ZZ = 4
MODE_H3_TRUNC_MOD8 = 5
MODE_H3_TRUNC_ZZ = 6
MODE_DENSE_FLOOR_MOD8 = 7
MODE_DENSE_FLOOR_ZZ = 8
MODE_DENSE_TRUNC_MOD8 = 9
MODE_DENSE_TRUNC_ZZ = 10

OUTER_MAGIC = b"K20O"
OUTER_VERSION = 1
OUTER_HDR = k17.OUTER_HDR
OUTER_ENT = k17.OUTER_ENT


def _sad(cur: np.ndarray, previous_y: np.ndarray, x0: int, y0: int, dx: int, dy: int):
    ref = previous_y[
        y0 + dy:y0 + dy + BLOCK,
        x0 + dx:x0 + dx + BLOCK,
    ].astype(np.int16)
    return int(np.abs(cur - ref).sum())


def _valid(x0: int, y0: int, dx: int, dy: int, w: int, h: int):
    sx = x0 + dx
    sy = y0 + dy
    return (
        sx >= 0
        and sy >= 0
        and sx + BLOCK <= w
        and sy + BLOCK <= h
    )


def _best_h3_luma(
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

    evaluated = {}
    sparse_ranked = []

    # Stage 1: existing 25 sparse-even vectors.
    for dx, dy in SPARSE:
        if not _valid(x0, y0, dx, dy, w, h):
            continue
        cost = _sad(cur, previous_y, x0, y0, dx, dy)
        dense_index = DENSE_INDEX[(dx, dy)]
        evaluated[(dx, dy)] = cost
        sparse_ranked.append((cost, dense_index, dx, dy))

    if not sparse_ranked:
        raise RuntimeError("H3 sparse stage found no valid candidate")

    sparse_ranked.sort()
    best = sparse_ranked[0]

    if best[0] == 0:
        cost, dense_index, dx, dy = best
        return cost, dense_index, dx, dy, len(evaluated)

    # Stage 2: refine the three best distinct sparse vectors.
    centers = sparse_ranked[:3]
    neighborhood = set()

    for _, _, center_dx, center_dy in centers:
        for dy in range(
            max(-RADIUS, center_dy - 1),
            min(RADIUS, center_dy + 1) + 1,
        ):
            for dx in range(
                max(-RADIUS, center_dx - 1),
                min(RADIUS, center_dx + 1) + 1,
            ):
                neighborhood.add((dx, dy))

    ordered = sorted(neighborhood, key=lambda v: DENSE_INDEX[v])

    for dx, dy in ordered:
        if (dx, dy) in evaluated:
            continue
        if not _valid(x0, y0, dx, dy, w, h):
            continue

        cost = _sad(cur, previous_y, x0, y0, dx, dy)
        dense_index = DENSE_INDEX[(dx, dy)]
        evaluated[(dx, dy)] = cost
        key = (cost, dense_index, dx, dy)

        if key < best:
            best = key

        if cost == 0:
            break

    cost, dense_index, dx, dy = best
    return cost, dense_index, dx, dy, len(evaluated)


def h3_motion_residuals(
    frame: bytes,
    previous: bytes,
    w: int,
    h: int,
):
    cy, cu, cv = k17.split_np(frame, w, h)
    py, pu, pv = k17.split_np(previous, w, h)

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
    eval_sum = 0
    nonzero = 0
    manhattan_sum = 0
    luma_sad_sum = 0

    k = 0

    for by in range(bh):
        y0 = by * BLOCK
        for bx in range(bw):
            x0 = bx * BLOCK

            cost, index, dx, dy, evals = _best_h3_luma(
                cy, py, x0, y0, w, h
            )

            motion[k] = index
            k += 1

            eval_sum += evals
            luma_sad_sum += cost
            manhattan_sum += abs(dx) + abs(dy)
            if dx != 0 or dy != 0:
                nonzero += 1
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
                (k17.CHROMA_FLOOR, floor_u, floor_v),
                (k17.CHROMA_TRUNC, trunc_u, trunc_v),
            ):
                cdx = k17.chroma_shift(dx, policy)
                cdy = k17.chroma_shift(dy, policy)

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
    luma = ry.tobytes()

    residuals = {
        k17.CHROMA_FLOOR: luma + floor_u.tobytes() + floor_v.tobytes(),
        k17.CHROMA_TRUNC: luma + trunc_u.tobytes() + trunc_v.tobytes(),
    }

    stats = {
        "total_blocks": total_blocks,
        "mean_candidate_evaluations": (
            eval_sum / total_blocks if total_blocks else 0.0
        ),
        "odd_any_fraction": (
            odd_any / total_blocks if total_blocks else 0.0
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

    return bytes(motion), residuals, stats


def build_h3_records(raw_chunk: bytes, w: int, h: int, gop: int):
    fs = k13.frame_size(w, h)
    total = len(raw_chunk) // fs
    chunks = []
    stats = []

    t0 = time.perf_counter()
    off = 0

    while off < total:
        n = min(gop, total - off)
        records = []
        previous = None

        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]

            if previous is None:
                records.append(("I", spatial_frame(frame, w, h)))
            else:
                motion, residuals, st = h3_motion_residuals(
                    frame, previous, w, h
                )
                records.append((
                    "P",
                    motion,
                    residuals[k17.CHROMA_FLOOR],
                    residuals[k17.CHROMA_TRUNC],
                ))
                stats.append(st)

            previous = frame

        chunks.append((n, records))
        off += n

    return chunks, stats, time.perf_counter() - t0


def h3_candidates_for_window(
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
    chunks, stats, search_seconds = build_h3_records(
        raw_chunk, w, h, gop
    )

    mean_evals = (
        sum(s["mean_candidate_evaluations"] for s in stats) / len(stats)
        if stats else 0.0
    )
    mean_odd = (
        sum(s["odd_any_fraction"] for s in stats) / len(stats)
        if stats else 0.0
    )

    rows = []
    configs = (
        (k17.CHROMA_FLOOR, k17.DENSE_MOD8, "H3_FLOOR_MOD8", MODE_H3_FLOOR_MOD8),
        (k17.CHROMA_FLOOR, k17.DENSE_ZZ, "H3_FLOOR_ZZ", MODE_H3_FLOOR_ZZ),
        (k17.CHROMA_TRUNC, k17.DENSE_MOD8, "H3_TRUNC_MOD8", MODE_H3_TRUNC_MOD8),
        (k17.CHROMA_TRUNC, k17.DENSE_ZZ, "H3_TRUNC_ZZ", MODE_H3_TRUNC_ZZ),
    )

    for chroma_policy, residual_mode, label, outer_mode in configs:
        t0 = time.perf_counter()
        front = k17.serialize_dense(
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
            front, exe, tmp, f"{tag}.{label.lower()}"
        )

        rows.append({
            "mode": outer_mode,
            "label": label,
            "payload": payload,
            "frontend_seconds": search_seconds + serialization_seconds,
            "backend_seconds": backend_seconds,
            "search_seconds": search_seconds,
            "mean_candidate_evaluations": mean_evals,
            "mean_odd_fraction": mean_odd,
        })

    return rows, search_seconds


def choose(candidates):
    return min(candidates, key=lambda x: (len(x["payload"]), x["mode"]))


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
            OUTER_MAGIC, OUTER_VERSION,
            w, h, fpsn, fpsd, gop, route_span
        ))
        for entry in entries:
            payload = entry["payload"]
            f.write(OUTER_ENT.pack(
                entry["mode"], entry["frames"], len(payload)
            ))
            f.write(payload)


def decode_outer(src: Path, dst: Path, exe: Path):
    data = src.read_bytes()
    if len(data) < OUTER_HDR.size:
        raise ValueError("truncated KSV-20 outer header")

    (
        magic, version, w, h, fpsn, fpsd, gop, route_span
    ) = OUTER_HDR.unpack_from(data, 0)

    if magic != OUTER_MAGIC or version != OUTER_VERSION:
        raise ValueError("bad KSV-20 outer stream")

    del fpsn, fpsd, gop, route_span

    pos = OUTER_HDR.size
    out = bytearray()

    with tempfile.TemporaryDirectory(prefix="ksv20_dec_") as td:
        tmp = Path(td)
        index = 0

        while pos < len(data):
            if pos + OUTER_ENT.size > len(data):
                raise ValueError("truncated KSV-20 outer entry")

            mode, frames, payload_size = OUTER_ENT.unpack_from(data, pos)
            pos += OUTER_ENT.size

            if pos + payload_size > len(data):
                raise ValueError("truncated KSV-20 outer payload")

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
                MODE_H3_FLOOR_MOD8,
                MODE_H3_FLOOR_ZZ,
                MODE_H3_TRUNC_MOD8,
                MODE_H3_TRUNC_ZZ,
                MODE_DENSE_FLOOR_MOD8,
                MODE_DENSE_FLOOR_ZZ,
                MODE_DENSE_TRUNC_MOD8,
                MODE_DENSE_TRUNC_ZZ,
            ):
                chunk = k17.decode_dense_front(front.read_bytes())
            else:
                raise ValueError("unknown KSV-20 mode")

            if len(chunk) != frames * k13.frame_size(w, h):
                raise ValueError("KSV-20 decoded frame count mismatch")

            out.extend(chunk)
            index += 1

    dst.write_bytes(out)


def policy_stats(entries):
    return dict(sorted(Counter(e["label"] for e in entries).items()))


def baseline_candidates(raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, tag):
    temp, sparse, sparse_seconds = k17.baseline_candidates(
        raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, tag
    )
    return temp, sparse, sparse_seconds


def dense_candidates(raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, tag):
    dense, seconds = k17.dense_candidates_for_window(
        raw_chunk, exe, tmp, w, h, fpsn, fpsd, gop, tag
    )
    # Re-map outer mode IDs; payload/front format remains K17D.
    mode_map = {
        k17.MODE_DENSE_FLOOR_MOD8: MODE_DENSE_FLOOR_MOD8,
        k17.MODE_DENSE_FLOOR_ZZ: MODE_DENSE_FLOOR_ZZ,
        k17.MODE_DENSE_TRUNC_MOD8: MODE_DENSE_TRUNC_MOD8,
        k17.MODE_DENSE_TRUNC_ZZ: MODE_DENSE_TRUNC_ZZ,
    }
    out = []
    for row in dense:
        r = dict(row)
        r["mode"] = mode_map[r["mode"]]
        r["label"] = "FULL_" + r["label"]
        out.append(r)
    return out, seconds


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
    h3_entries = []
    dense_entries = []
    windows = []

    baseline_research_seconds = 0.0
    h3_research_seconds = 0.0
    dense_research_seconds = 0.0

    with tempfile.TemporaryDirectory(prefix="ksv20_enc_") as td:
        tmp = Path(td)

        for window_index, off in enumerate(range(0, total, route_span)):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, sparse, sparse_seconds = baseline_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{window_index}"
            )
            h3_rows, h3_seconds = h3_candidates_for_window(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{window_index}"
            )
            dense, dense_seconds = dense_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{window_index}"
            )

            baseline = choose([temp, *sparse])
            h3_policy = choose([temp, *h3_rows])
            dense_policy = choose([temp, *dense])

            for e in (baseline, h3_policy, dense_policy):
                e["frames"] = n

            baseline_entries.append(dict(baseline))
            h3_entries.append(dict(h3_policy))
            dense_entries.append(dict(dense_policy))

            temp_cost = temp["frontend_seconds"] + temp["backend_seconds"]
            sparse_cost = sparse_seconds + sum(x["backend_seconds"] for x in sparse)
            h3_cost = h3_seconds + sum(x["backend_seconds"] for x in h3_rows)
            dense_cost = dense_seconds + sum(x["backend_seconds"] for x in dense)

            baseline_research_seconds += temp_cost + sparse_cost
            h3_research_seconds += temp_cost + h3_cost
            dense_research_seconds += temp_cost + dense_cost

            best_h3 = choose(h3_rows)
            best_dense = choose(dense)

            windows.append({
                "window": window_index,
                "frames": n,
                "baseline_selected": baseline["label"],
                "h3_selected": h3_policy["label"],
                "dense_selected": dense_policy["label"],
                "h3_bytes": len(h3_policy["payload"]),
                "dense_bytes": len(dense_policy["payload"]),
                "h3_search_seconds": best_h3["search_seconds"],
                "dense_search_seconds": best_dense["search_seconds"],
                "h3_mean_candidate_evaluations": best_h2[
                    "mean_candidate_evaluations"
                ],
                "h3_mean_odd_fraction": best_h3["mean_odd_fraction"],
                "dense_mean_odd_fraction": best_dense["mean_odd_fraction"],
            })

    paths = {
        "baseline": prefix.with_suffix(".baseline.k20"),
        "h3": prefix.with_suffix(".h3.k20"),
        "dense": prefix.with_suffix(".dense.k20"),
    }

    for key, entries in (
        ("baseline", baseline_entries),
        ("h3", h3_entries),
        ("dense", dense_entries),
    ):
        write_outer(
            paths[key], w, h, fpsn, fpsd, gop, route_span, entries
        )

    return {
        "paths": paths,
        "baseline": {
            "bytes": paths["baseline"].stat().st_size,
            "encode_research_seconds": baseline_research_seconds,
            "modes": policy_stats(baseline_entries),
        },
        "h3": {
            "bytes": paths["h3"].stat().st_size,
            "encode_research_seconds": h3_research_seconds,
            "modes": policy_stats(h3_entries),
        },
        "dense": {
            "bytes": paths["dense"].stat().st_size,
            "encode_research_seconds": dense_research_seconds,
            "modes": policy_stats(dense_entries),
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
        enc = encode_source(
            src, OUT / clip["name"], args.kephir,
            clip["w"], clip["h"], clip["fpsn"], clip["fpsd"]
        )

        decoded = {}
        for policy in ("baseline", "h3", "dense"):
            dst = OUT / f"{clip['name']}.{policy}.decoded.yuv"
            t0 = time.perf_counter()
            decode_outer(enc["paths"][policy], dst, args.kephir)
            seconds = time.perf_counter() - t0
            ok = k13.sha_file(dst) == k13.sha_file(src)
            if not ok:
                raise RuntimeError(f"{clip['name']} {policy}: SHA mismatch")
            decoded[policy] = {"decode_seconds": seconds, "sha_ok": True}

        raw_bytes = src.stat().st_size
        row = {
            "name": clip["name"],
            "raw_bytes": raw_bytes,
            "baseline": {**enc["baseline"], **decoded["baseline"]},
            "h3": {**enc["h3"], **decoded["h3"]},
            "dense": {**enc["dense"], **decoded["dense"]},
            "windows": enc["windows"],
        }

        for policy in ("baseline", "h3", "dense"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        dense_gain = row["baseline"]["bytes"] - row["dense"]["bytes"]
        h3_gain = row["baseline"]["bytes"] - row["h3"]["bytes"]

        row["h3_delta_percent"] = (
            100.0 * (row["h3"]["bytes"] / row["baseline"]["bytes"] - 1.0)
        )
        row["dense_delta_percent"] = (
            100.0 * (row["dense"]["bytes"] / row["baseline"]["bytes"] - 1.0)
        )
        row["gain_recovered_percent"] = (
            100.0 * h3_gain / dense_gain if dense_gain > 0 else 0.0
        )

        rows.append(row)

        print(
            "KSV20_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "h3", row["h3"]["bytes"],
            "dense", row["dense"]["bytes"],
            "h3_delta_pct", f"{row['h3_delta_percent']:.6f}",
            "dense_delta_pct", f"{row['dense_delta_percent']:.6f}",
            "recovered_pct", f"{row['gain_recovered_percent']:.3f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)
    aggregate = {}
    for policy in ("baseline", "h3", "dense"):
        total = sum(r[policy]["bytes"] for r in rows)
        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": 100.0 * total / raw_total,
            "encode_research_seconds": sum(
                r[policy]["encode_research_seconds"] for r in rows
            ),
        }

    dense_gain = aggregate["baseline"]["bytes"] - aggregate["dense"]["bytes"]
    h3_gain = aggregate["baseline"]["bytes"] - aggregate["h3"]["bytes"]

    aggregate["h3_delta_percent"] = (
        100.0 * (
            aggregate["h3"]["bytes"] / aggregate["baseline"]["bytes"] - 1.0
        )
    )
    aggregate["dense_delta_percent"] = (
        100.0 * (
            aggregate["dense"]["bytes"] / aggregate["baseline"]["bytes"] - 1.0
        )
    )
    aggregate["gain_recovered_percent"] = (
        100.0 * h3_gain / dense_gain if dense_gain > 0 else 0.0
    )
    aggregate["h3_vs_dense_search_time_ratio"] = (
        aggregate["h3"]["encode_research_seconds"]
        / aggregate["dense"]["encode_research_seconds"]
        if aggregate["dense"]["encode_research_seconds"] > 0
        else 0.0
    )

    result = {
        "experiment": "KSV-20 H3 hierarchical dense refinement",
        "sparse_candidate_count": 25,
        "dense_candidate_count": 81,
        "hierarchical_policy": "three best sparse-even vectors + union of unique 3x3 integer neighborhoods",
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "H3 and exhaustive dense use the same K17D motion-map semantics.",
            "H3 evaluates approximately 25-49 candidates/block instead of 81.",
            "FLOOR/TRUNC chroma and MOD8/ZZ_INTER are both evaluated.",
            "Every emitted stream is independently decoded and SHA verified.",
            "Research encode time includes duplicate candidate KHEPRI encodes.",
        ],
    }

    (OUT / "KSV20_RESULTS.json").write_text(json.dumps(result, indent=2))

    print("KSV20_HIERARCHICAL_DENSE_H3_PASS")
    print(
        "KSV20_AGGREGATE",
        "baseline", aggregate["baseline"]["bytes"],
        "h3", aggregate["h3"]["bytes"],
        "dense", aggregate["dense"]["bytes"],
        "h3_delta_pct", f"{aggregate['h3_delta_percent']:.6f}",
        "dense_delta_pct", f"{aggregate['dense_delta_percent']:.6f}",
        "recovered_pct", f"{aggregate['gain_recovered_percent']:.3f}",
        "h3_vs_dense_research_time_ratio",
        f"{aggregate['h3_vs_dense_search_time_ratio']:.4f}",
    )


if __name__ == "__main__":
    main()
