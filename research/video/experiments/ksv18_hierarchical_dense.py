#!/usr/bin/env python3
"""
KSV-18 Hierarchical Dense Refinement.

Quality target:
KSV-17 exhaustive dense integer MC8R4:
- 81 integer vectors/block;
- 518,713-byte maximum sparse+dense oracle gain on Natural Video Corpus v1.

Production hypothesis:
retain the existing 25 even-grid candidates as a coarse pass, then refine only
the 1-pixel neighborhood around the best K coarse centers.

Variants:
- K1: refine around best 1 coarse vector;
- K2: refine around best 2 coarse vectors;
- K4: refine around best 4 coarse vectors.

Every variant:
- uses the exact KSV-17 81-code motion-map semantics;
- tests FLOOR and TRUNC YUV420 chroma mapping;
- tests MOD8 and ZZ_INTER residual mappings;
- keeps baseline TEMP/sparse candidates as a final-size fallback.

The workflow also runs the full KSV-17 dense oracle as the quality ceiling and
reports how much of that byte gain each hierarchical variant recovers.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

import ksv17_dense_integer_motion as k17
import ksv13_natural_radius_sweep as k13
from kstream_video_motion_control import candidates as sparse_candidates
from kstream_video_baseline import spatial_frame

OUT = Path("results/video/ksv18_hierarchical_dense")

BLOCK = 8
RADIUS = 4
K_VALUES = (1, 2, 4)

SPARSE_CANDIDATES = sparse_candidates(RADIUS)
DENSE_CANDIDATES = k17.DENSE_CANDIDATES
DENSE_INDEX = {p: i for i, p in enumerate(DENSE_CANDIDATES)}

if len(SPARSE_CANDIDATES) != 25:
    raise RuntimeError("unexpected sparse candidate count")
if len(DENSE_CANDIDATES) != 81:
    raise RuntimeError("unexpected dense candidate count")


def _valid_vector(x0: int, y0: int, dx: int, dy: int, w: int, h: int):
    sx = x0 + dx
    sy = y0 + dy
    return (
        sx >= 0
        and sy >= 0
        and sx + BLOCK <= w
        and sy + BLOCK <= h
    )


def _sad(
    current_y: np.ndarray,
    previous_y: np.ndarray,
    x0: int,
    y0: int,
    dx: int,
    dy: int,
):
    cur = current_y[
        y0:y0 + BLOCK,
        x0:x0 + BLOCK,
    ].astype(np.int16)

    ref = previous_y[
        y0 + dy:y0 + dy + BLOCK,
        x0 + dx:x0 + dx + BLOCK,
    ].astype(np.int16)

    return int(np.abs(cur - ref).sum())


def _refinement_indices(
    top_coarse,
    k: int,
    x0: int,
    y0: int,
    w: int,
    h: int,
):
    indices = set()

    # Every sparse-even candidate stays available.
    for dx, dy in SPARSE_CANDIDATES:
        if _valid_vector(x0, y0, dx, dy, w, h):
            indices.add(DENSE_INDEX[(dx, dy)])

    # Add the dense 3x3 neighborhood around the best K coarse centers.
    for _, _, _, cdx, cdy in top_coarse[:k]:
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                dx = cdx + ox
                dy = cdy + oy
                if not (-RADIUS <= dx <= RADIUS):
                    continue
                if not (-RADIUS <= dy <= RADIUS):
                    continue
                if not _valid_vector(x0, y0, dx, dy, w, h):
                    continue
                indices.add(DENSE_INDEX[(dx, dy)])

    return indices


def hierarchical_motion_residuals(
    frame: bytes,
    previous: bytes,
    w: int,
    h: int,
    k_refine: int,
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

    evaluation_sum = 0
    odd_blocks = 0
    nonzero_blocks = 0
    manhattan_sum = 0
    luma_sad_sum = 0

    q = 0

    for by in range(bh):
        y0 = by * BLOCK

        for bx in range(bw):
            x0 = bx * BLOCK

            costs = {}
            coarse = []

            for sparse_order, (dx, dy) in enumerate(SPARSE_CANDIDATES):
                if not _valid_vector(x0, y0, dx, dy, w, h):
                    continue

                dense_index = DENSE_INDEX[(dx, dy)]
                cost = _sad(cy, py, x0, y0, dx, dy)
                costs[dense_index] = cost
                coarse.append(
                    (cost, sparse_order, dense_index, dx, dy)
                )

            if not coarse:
                raise RuntimeError("KSV-18 coarse search found no candidate")

            coarse.sort(key=lambda row: (row[0], row[1]))

            candidate_indices = _refinement_indices(
                coarse, k_refine, x0, y0, w, h
            )

            for dense_index in candidate_indices:
                if dense_index in costs:
                    continue

                dx, dy = DENSE_CANDIDATES[dense_index]
                costs[dense_index] = _sad(
                    cy, py, x0, y0, dx, dy
                )

            # Match exhaustive KSV-17 tie semantics: first dense-order minimum.
            best_index = min(
                candidate_indices,
                key=lambda idx: (costs[idx], idx),
            )
            best_cost = costs[best_index]
            dx, dy = DENSE_CANDIDATES[best_index]

            motion[q] = best_index
            q += 1

            evaluation_sum += len(candidate_indices)
            luma_sad_sum += best_cost
            manhattan_sum += abs(dx) + abs(dy)

            if dx != 0 or dy != 0:
                nonzero_blocks += 1
            if (dx & 1) or (dy & 1):
                odd_blocks += 1

            cur = cy[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ].astype(np.int16)

            pred = py[
                y0 + dy:y0 + dy + BLOCK,
                x0 + dx:x0 + dx + BLOCK,
            ].astype(np.int16)

            ry[
                y0:y0 + BLOCK,
                x0:x0 + BLOCK,
            ] = ((cur - pred) & 255).astype(np.uint8)

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

    residuals = {
        k17.CHROMA_FLOOR: (
            ry.tobytes()
            + floor_u.tobytes()
            + floor_v.tobytes()
        ),
        k17.CHROMA_TRUNC: (
            ry.tobytes()
            + trunc_u.tobytes()
            + trunc_v.tobytes()
        ),
    }

    stats = {
        "k_refine": k_refine,
        "total_blocks": total_blocks,
        "mean_candidate_evaluations": (
            evaluation_sum / total_blocks
            if total_blocks else 0.0
        ),
        "odd_fraction": (
            odd_blocks / total_blocks
            if total_blocks else 0.0
        ),
        "nonzero_fraction": (
            nonzero_blocks / total_blocks
            if total_blocks else 0.0
        ),
        "mean_manhattan": (
            manhattan_sum / total_blocks
            if total_blocks else 0.0
        ),
        "mean_luma_sad": (
            luma_sad_sum / total_blocks
            if total_blocks else 0.0
        ),
    }

    return bytes(motion), residuals, stats


def build_hier_records(
    raw_chunk: bytes,
    w: int,
    h: int,
    gop: int,
    k_refine: int,
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
            frame = raw_chunk[
                (off + j) * fs:(off + j + 1) * fs
            ]

            if previous is None:
                records.append(
                    ("I", spatial_frame(frame, w, h))
                )
            else:
                motion, residuals, stats = (
                    hierarchical_motion_residuals(
                        frame,
                        previous,
                        w,
                        h,
                        k_refine,
                    )
                )

                records.append(
                    (
                        "P",
                        motion,
                        residuals[k17.CHROMA_FLOOR],
                        residuals[k17.CHROMA_TRUNC],
                    )
                )
                frame_stats.append(stats)

            previous = frame

        chunks.append((n, records))
        off += n

    return (
        chunks,
        frame_stats,
        time.perf_counter() - t0,
    )


def hierarchical_candidates_for_window(
    raw_chunk: bytes,
    exe: Path,
    tmp: Path,
    w: int,
    h: int,
    fpsn: int,
    fpsd: int,
    gop: int,
    tag: str,
    k_refine: int,
):
    chunks, stats, search_seconds = build_hier_records(
        raw_chunk,
        w,
        h,
        gop,
        k_refine,
    )

    mean_evaluations = (
        sum(s["mean_candidate_evaluations"] for s in stats)
        / len(stats)
        if stats else 0.0
    )

    mean_odd_fraction = (
        sum(s["odd_fraction"] for s in stats)
        / len(stats)
        if stats else 0.0
    )

    rows = []

    configs = (
        (
            k17.CHROMA_FLOOR,
            k17.DENSE_MOD8,
            f"HIER_K{k_refine}_FLOOR_MOD8",
            k17.MODE_DENSE_FLOOR_MOD8,
        ),
        (
            k17.CHROMA_FLOOR,
            k17.DENSE_ZZ,
            f"HIER_K{k_refine}_FLOOR_ZZ",
            k17.MODE_DENSE_FLOOR_ZZ,
        ),
        (
            k17.CHROMA_TRUNC,
            k17.DENSE_MOD8,
            f"HIER_K{k_refine}_TRUNC_MOD8",
            k17.MODE_DENSE_TRUNC_MOD8,
        ),
        (
            k17.CHROMA_TRUNC,
            k17.DENSE_ZZ,
            f"HIER_K{k_refine}_TRUNC_ZZ",
            k17.MODE_DENSE_TRUNC_ZZ,
        ),
    )

    for chroma_policy, residual_mode, label, outer_mode in configs:
        t0 = time.perf_counter()

        # KSV-18 uses exactly the KSV-17 dense bitstream semantics.
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
            "mean_candidate_evaluations": mean_evaluations,
            "mean_odd_fraction": mean_odd_fraction,
        })

    return rows, search_seconds


def choose(candidates):
    return min(
        candidates,
        key=lambda row: (
            len(row["payload"]),
            row["mode"],
            row.get("label", ""),
        ),
    )


def policy_stats(entries):
    return dict(
        sorted(Counter(e["label"] for e in entries).items())
    )


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

    policies = {
        "baseline": [],
        "k1": [],
        "k2": [],
        "k4": [],
        "full": [],
    }

    windows = []

    with tempfile.TemporaryDirectory(prefix="ksv18_enc_") as td:
        tmp = Path(td)

        for window_index, off in enumerate(
            range(0, total, route_span)
        ):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp, sparse, sparse_search_seconds = (
                k17.baseline_candidates(
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
            )

            full_dense, full_search_seconds = (
                k17.dense_candidates_for_window(
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
            )

            hierarchical = {}
            for k_refine in K_VALUES:
                hierarchical[k_refine], _ = (
                    hierarchical_candidates_for_window(
                        chunk,
                        exe,
                        tmp,
                        w,
                        h,
                        fpsn,
                        fpsd,
                        gop,
                        f"w{window_index}",
                        k_refine,
                    )
                )

            selected = {
                "baseline": choose([temp, *sparse]),
                "k1": choose([
                    temp,
                    *sparse,
                    *hierarchical[1],
                ]),
                "k2": choose([
                    temp,
                    *sparse,
                    *hierarchical[2],
                ]),
                "k4": choose([
                    temp,
                    *sparse,
                    *hierarchical[4],
                ]),
                "full": choose([
                    temp,
                    *sparse,
                    *full_dense,
                ]),
            }

            for entry in selected.values():
                entry["frames"] = n

            for name, entry in selected.items():
                policies[name].append(dict(entry))

            full_best = choose(full_dense)

            window = {
                "window": window_index,
                "frames": n,
                "baseline_selected": selected[
                    "baseline"
                ]["label"],
                "full_selected": selected["full"]["label"],
                "full_dense_search_seconds": (
                    full_search_seconds
                ),
                "full_dense_bytes": len(
                    full_best["payload"]
                ),
            }

            for k_refine in K_VALUES:
                best_hier = choose(
                    hierarchical[k_refine]
                )

                window[f"k{k_refine}_selected"] = (
                    selected[f"k{k_refine}"]["label"]
                )
                window[f"k{k_refine}_best_hier_bytes"] = (
                    len(best_hier["payload"])
                )
                window[
                    f"k{k_refine}_mean_candidate_evaluations"
                ] = best_hier[
                    "mean_candidate_evaluations"
                ]
                window[
                    f"k{k_refine}_mean_odd_fraction"
                ] = best_hier["mean_odd_fraction"]
                window[
                    f"k{k_refine}_search_seconds"
                ] = best_hier["search_seconds"]

            windows.append(window)

    paths = {
        name: prefix.with_suffix(f".{name}.k18")
        for name in policies
    }

    for name, entries in policies.items():
        k17.write_outer(
            paths[name],
            w,
            h,
            fpsn,
            fpsd,
            gop,
            route_span,
            entries,
        )

    return {
        "paths": paths,
        "policies": {
            name: {
                "bytes": paths[name].stat().st_size,
                "modes": policy_stats(entries),
            }
            for name, entries in policies.items()
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


def gain_recovered(
    baseline_bytes: int,
    candidate_bytes: int,
    full_bytes: int,
):
    opportunity = baseline_bytes - full_bytes

    if opportunity <= 0:
        return 100.0 if candidate_bytes <= baseline_bytes else 0.0

    recovered = baseline_bytes - candidate_bytes
    return 100.0 * recovered / opportunity


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

        for policy in (
            "baseline",
            "k1",
            "k2",
            "k4",
            "full",
        ):
            dst = OUT / (
                f"{clip['name']}.{policy}.decoded.yuv"
            )

            t0 = time.perf_counter()
            k17.decode_outer(
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
            "windows": encoded["windows"],
        }

        for policy in (
            "baseline",
            "k1",
            "k2",
            "k4",
            "full",
        ):
            row[policy] = {
                **encoded["policies"][policy],
                **decoded[policy],
            }

            row[policy]["ratio_percent"] = (
                100.0
                * row[policy]["bytes"]
                / raw_bytes
            )

        for k_refine in K_VALUES:
            key = f"k{k_refine}"
            row[key]["gain_recovered_percent"] = (
                gain_recovered(
                    row["baseline"]["bytes"],
                    row[key]["bytes"],
                    row["full"]["bytes"],
                )
            )

        rows.append(row)

        print(
            "KSV18_SOURCE_PASS",
            clip["name"],
            "baseline", row["baseline"]["bytes"],
            "k1", row["k1"]["bytes"],
            "k2", row["k2"]["bytes"],
            "k4", row["k4"]["bytes"],
            "full", row["full"]["bytes"],
            "k1_recovered",
            f"{row['k1']['gain_recovered_percent']:.3f}",
            "k2_recovered",
            f"{row['k2']['gain_recovered_percent']:.3f}",
            "k4_recovered",
            f"{row['k4']['gain_recovered_percent']:.3f}",
            flush=True,
        )

    raw_total = sum(r["raw_bytes"] for r in rows)

    aggregate = {}

    for policy in (
        "baseline",
        "k1",
        "k2",
        "k4",
        "full",
    ):
        total = sum(
            r[policy]["bytes"] for r in rows
        )

        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": (
                100.0 * total / raw_total
            ),
        }

    for k_refine in K_VALUES:
        key = f"k{k_refine}"

        aggregate[key]["gain_recovered_percent"] = (
            gain_recovered(
                aggregate["baseline"]["bytes"],
                aggregate[key]["bytes"],
                aggregate["full"]["bytes"],
            )
        )

        eval_values = [
            w[f"k{k_refine}_mean_candidate_evaluations"]
            for row in rows
            for w in row["windows"]
        ]

        search_values = [
            w[f"k{k_refine}_search_seconds"]
            for row in rows
            for w in row["windows"]
        ]

        aggregate[key][
            "mean_candidate_evaluations"
        ] = (
            sum(eval_values) / len(eval_values)
            if eval_values else 0.0
        )

        aggregate[key]["search_seconds"] = (
            sum(search_values)
        )

    aggregate["full"]["search_seconds"] = sum(
        w["full_dense_search_seconds"]
        for row in rows
        for w in row["windows"]
    )

    result = {
        "experiment": "KSV-18 hierarchical dense refinement",
        "coarse_candidate_count": 25,
        "full_dense_candidate_count": 81,
        "refinement_k": list(K_VALUES),
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "Hierarchical variants always retain all 25 sparse-even candidates.",
            "Refinement adds unique dense 3x3 neighbors around the best K coarse centers.",
            "Motion codes remain KSV-17 dense 81-code indices.",
            "FLOOR/TRUNC chroma and MOD8/ZZ are evaluated for every hierarchical variant.",
            "Final policy includes sparse baseline candidates, so K1/K2/K4 cannot regress by construction.",
            "Full policy is the KSV-17 sparse+dense oracle quality ceiling.",
            "Every emitted stream is independently decoded and SHA verified.",
        ],
    }

    (OUT / "KSV18_RESULTS.json").write_text(
        json.dumps(result, indent=2)
    )

    print("KSV18_HIERARCHICAL_DENSE_PASS")

    for k_refine in K_VALUES:
        key = f"k{k_refine}"

        print(
            "KSV18_AGGREGATE",
            key,
            "bytes", aggregate[key]["bytes"],
            "gain_recovered_pct",
            f"{aggregate[key]['gain_recovered_percent']:.3f}",
            "mean_evals",
            f"{aggregate[key]['mean_candidate_evaluations']:.3f}",
            "search_seconds",
            f"{aggregate[key]['search_seconds']:.6f}",
        )

    print(
        "KSV18_FULL",
        "baseline_bytes",
        aggregate["baseline"]["bytes"],
        "full_bytes",
        aggregate["full"]["bytes"],
        "full_search_seconds",
        f"{aggregate['full']['search_seconds']:.6f}",
    )


if __name__ == "__main__":
    main()
