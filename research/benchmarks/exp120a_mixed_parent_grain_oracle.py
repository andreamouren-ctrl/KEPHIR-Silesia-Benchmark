#!/usr/bin/env python3
"""EXP-120A — mixed parent-grain / local-policy oracle.

This experiment intentionally does NOT change the K75 bitstream.
It asks a narrower question first: if a file could change the parent-grain
family inside the file, is there enough byte value to justify a format change?

Method:
- reproduce the qualified EXP-118B whole-file policy (2 MiB stratified probe,
  margin 0, choices adaptive/grain4/grain8);
- split each corpus file independently at 4/8/16 MiB research boundaries;
- compress every segment with adaptive/grain2/grain4/grain8;
- compare local oracles by compressed K75 blob bytes, excluding the temporary
  KPF1 filename wrapper from the choice;
- verify the selected segment candidate by exact SHA-256 roundtrip;
- report both an optimistic no-reset projection and the actually observed
  independent-segment result, so context-reset cost is explicit rather than
  hidden.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

MiB = 1024 * 1024
STRICT_28_MAX_BYTES = 59_342_802
EXPECTED_EXP118B_SILESIA = 60_963_390
EXPECTED_EXP118B_EXTERNAL = 4_792_947

BASE_CANDIDATES = {
    "adaptive": ["adaptive"],
    "grain4": ["4096", "4096", "1"],
    "grain8": ["8192", "8192", "1"],
}
CANDIDATES = {
    "adaptive": ["adaptive"],
    "grain2": ["2048", "2048", "1"],
    "grain4": ["4096", "4096", "1"],
    "grain8": ["8192", "8192", "1"],
}
SEGMENT_SIZES = [4 * MiB, 8 * MiB, 16 * MiB]
FRAME_OVERHEADS = [0, 4, 16, 64]
PROBE_BYTES = 2 * MiB


def run(cmd):
    p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    out = {}
    for line in p.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(MiB), b""):
            h.update(block)
    return h.hexdigest()


def get_varint(data: bytes, pos: int):
    value = 0
    shift = 0
    for _ in range(10):
        if pos >= len(data):
            raise ValueError("truncated varint")
        b = data[pos]
        pos += 1
        payload = b & 0x7F
        if shift == 63 and payload > 1:
            raise ValueError("varint overflow")
        value |= payload << shift
        if not (b & 0x80):
            return value, pos
        shift += 7
    raise ValueError("varint overflow")


def kpf1_file_blob_size(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 5 or data[:4] != b"KPF1" or data[4] != 0:
        raise ValueError(f"not a KPF1 file archive: {path}")
    pos = 5
    name_len, pos = get_varint(data, pos)
    if name_len > len(data) - pos:
        raise ValueError("truncated KPF1 name")
    pos += name_len
    blob_len, pos = get_varint(data, pos)
    if blob_len > len(data) - pos or pos + blob_len != len(data):
        raise ValueError("invalid KPF1 blob framing")
    return blob_len


def dataset_files():
    silesia = sorted(p for p in Path("corpora/silesia").rglob("*") if p.is_file())
    external = []
    for root_name in ("canterbury", "calgary", "large"):
        root = Path("corpora") / root_name
        external.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    return {"silesia": silesia, "external": external}


def file_id(dataset: str, path: Path) -> str:
    return path.name if dataset == "silesia" else str(path.relative_to("corpora"))


def stratified_sample(data: bytes, budget: int = PROBE_BYTES) -> bytes:
    if len(data) <= budget:
        return data
    parts = 4
    chunk = max(1, budget // parts)
    maxoff = len(data) - chunk
    offsets = [(maxoff * i) // (parts - 1) for i in range(parts)]
    out = bytearray()
    for off in offsets:
        remaining = budget - len(out)
        if remaining <= 0:
            break
        out.extend(data[off:off + min(chunk, remaining)])
    return bytes(out[:budget])


def compress(cli: Path, src: Path, archive: Path, extra):
    result = run([str(cli), "c", str(src), str(archive), "4", *extra])
    archive_bytes = int(result["OUTPUT_BYTES"])
    actual = archive.stat().st_size
    if actual != archive_bytes:
        raise RuntimeError("CLI/archive byte accounting mismatch")
    blob_bytes = kpf1_file_blob_size(archive)
    return {
        "archive_bytes": archive_bytes,
        "blob_bytes": blob_bytes,
        "outer_bytes": archive_bytes - blob_bytes,
        "seconds": float(result["SECONDS"]),
    }


def verify_archive(cli: Path, archive: Path, expected: Path, outdir: Path):
    shutil.rmtree(outdir, ignore_errors=True)
    run([str(cli), "d", str(archive), str(outdir), "4"])
    restored = outdir / expected.name
    if not restored.is_file() or sha256(restored) != sha256(expected):
        raise RuntimeError(f"roundtrip failed: {expected}")
    shutil.rmtree(outdir, ignore_errors=True)


def choose_118b(probe_rows):
    adaptive = probe_rows["adaptive"]["archive_bytes"]
    grain = min(
        ("grain4", "grain8"),
        key=lambda k: (probe_rows[k]["archive_bytes"], 0 if k == "grain4" else 1),
    )
    return grain if probe_rows[grain]["archive_bytes"] < adaptive else "adaptive"


def measure_whole_file(cli: Path, dataset: str, path: Path, work: Path, index: int):
    rows = {}
    archives = {}
    for name, extra in CANDIDATES.items():
        archive = work / f"whole_{index:03d}_{name}.kpf"
        rows[name] = compress(cli, path, archive, extra)
        archives[name] = archive

    data = path.read_bytes()
    sample = work / f"probe_{index:03d}.bin"
    sample.write_bytes(stratified_sample(data))
    probe_rows = {}
    for name, extra in BASE_CANDIDATES.items():
        archive = work / f"probe_{index:03d}_{name}.kpf"
        probe_rows[name] = compress(cli, sample, archive, extra)
        archive.unlink(missing_ok=True)
    sample.unlink(missing_ok=True)

    choice = choose_118b(probe_rows)
    verify_archive(
        cli,
        archives[choice],
        path,
        work / f"whole_verify_{index:03d}",
    )
    selected = rows[choice]

    for archive in archives.values():
        archive.unlink(missing_ok=True)

    return {
        "dataset": dataset,
        "file": file_id(dataset, path),
        "raw_bytes": path.stat().st_size,
        "candidates": rows,
        "probe": probe_rows,
        "exp118b_choice": choice,
        "selected_archive_bytes": selected["archive_bytes"],
        "selected_blob_bytes": selected["blob_bytes"],
        "selected_outer_bytes": selected["outer_bytes"],
    }


def split_file(path: Path, chunk_bytes: int, work: Path, token: str):
    chunks = []
    with path.open("rb") as source:
        i = 0
        while True:
            data = source.read(chunk_bytes)
            if not data:
                break
            # The basename is deliberately stable so all candidates have the
            # same KPF1 wrapper overhead. We compare K75 blob bytes anyway.
            chunk_dir = work / f"chunk_{token}_{i:03d}"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunk = chunk_dir / "chunk.bin"
            chunk.write_bytes(data)
            chunks.append(chunk)
            i += 1
    if not chunks:
        chunk_dir = work / f"chunk_{token}_000"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk = chunk_dir / "chunk.bin"
        chunk.write_bytes(b"")
        chunks.append(chunk)
    return chunks


def measure_segments(
    cli: Path,
    path: Path,
    full_choice: str,
    outer_bytes: int,
    segment_bytes: int,
    work: Path,
    index: int,
):
    chunks = split_file(
        path,
        segment_bytes,
        work,
        f"{index:03d}_{segment_bytes // MiB}m",
    )

    inherited_blob = 0
    adaptive_blob = 0
    existing_oracle_blob = 0
    extended_oracle_blob = 0
    existing_winners = Counter()
    extended_winners = Counter()
    candidate_blob_totals = Counter()
    chunk_rows = []

    for chunk_index, chunk in enumerate(chunks):
        rows = {}
        archives = {}
        for name, extra in CANDIDATES.items():
            archive = chunk.parent / f"{name}.kpf"
            rows[name] = compress(cli, chunk, archive, extra)
            archives[name] = archive
            candidate_blob_totals[name] += rows[name]["blob_bytes"]

        existing = min(
            BASE_CANDIDATES,
            key=lambda k: (rows[k]["blob_bytes"], list(BASE_CANDIDATES).index(k)),
        )
        extended = min(
            CANDIDATES,
            key=lambda k: (rows[k]["blob_bytes"], list(CANDIDATES).index(k)),
        )

        verify_archive(
            cli,
            archives[extended],
            chunk,
            chunk.parent / "verify_out",
        )

        inherited_blob += rows[full_choice]["blob_bytes"]
        adaptive_blob += rows["adaptive"]["blob_bytes"]
        existing_oracle_blob += rows[existing]["blob_bytes"]
        extended_oracle_blob += rows[extended]["blob_bytes"]
        existing_winners[existing] += 1
        extended_winners[extended] += 1

        chunk_rows.append({
            "index": chunk_index,
            "raw_bytes": chunk.stat().st_size,
            "candidates": rows,
            "inherited_choice": full_choice,
            "existing_oracle": existing,
            "extended_oracle": extended,
        })

        for archive in archives.values():
            archive.unlink(missing_ok=True)
        shutil.rmtree(chunk.parent, ignore_errors=True)

    count = len(chunks)
    local_existing_gain = inherited_blob - existing_oracle_blob
    grain2_gain = existing_oracle_blob - extended_oracle_blob
    total_local_gain = inherited_blob - extended_oracle_blob

    realized = {}
    for overhead in FRAME_OVERHEADS:
        realized[str(overhead)] = (
            outer_bytes + extended_oracle_blob + overhead * count
        )

    return {
        "segment_bytes": segment_bytes,
        "segment_mib": segment_bytes // MiB,
        "chunk_count": count,
        "inherited_blob_bytes": inherited_blob,
        "adaptive_blob_bytes": adaptive_blob,
        "existing_oracle_blob_bytes": existing_oracle_blob,
        "extended_oracle_blob_bytes": extended_oracle_blob,
        "local_existing_mix_gain": local_existing_gain,
        "grain2_incremental_gain": grain2_gain,
        "total_local_gain": total_local_gain,
        "candidate_blob_totals": dict(candidate_blob_totals),
        "existing_winners": dict(existing_winners),
        "extended_winners": dict(extended_winners),
        "realized_independent_archive_bytes": realized,
        "chunks": chunk_rows,
    }


def summarize_dataset(dataset: str, files, segment_sizes):
    raw = sum(r["raw_bytes"] for r in files)
    selected = sum(r["selected_archive_bytes"] for r in files)
    out = {
        "dataset": dataset,
        "raw_bytes": raw,
        "file_count": len(files),
        "exp118b_selected_bytes": selected,
        "exp118b_selected_ratio": selected / raw if raw else 0.0,
        "segment_sizes": {},
    }

    for segment_bytes in segment_sizes:
        key = str(segment_bytes // MiB)
        rows = [r["segments"][key] for r in files]
        chunks = sum(r["chunk_count"] for r in rows)
        local_existing = sum(r["local_existing_mix_gain"] for r in rows)
        grain2_gain = sum(r["grain2_incremental_gain"] for r in rows)
        total_gain = sum(r["total_local_gain"] for r in rows)
        realized = {
            str(overhead): sum(
                r["realized_independent_archive_bytes"][str(overhead)]
                for r in rows
            )
            for overhead in FRAME_OVERHEADS
        }
        projected = {
            str(overhead): selected - total_gain + overhead * chunks
            for overhead in FRAME_OVERHEADS
        }
        reset_penalty = {
            str(overhead): realized[str(overhead)] - projected[str(overhead)]
            for overhead in FRAME_OVERHEADS
        }
        winners = Counter()
        for r in rows:
            winners.update(r["extended_winners"])

        summary = {
            "segment_bytes": segment_bytes,
            "segment_mib": segment_bytes // MiB,
            "chunk_count": chunks,
            "local_existing_mix_gain": local_existing,
            "grain2_incremental_gain": grain2_gain,
            "total_local_gain": total_gain,
            "projected_archive_bytes": projected,
            "projected_ratio": {
                k: v / raw if raw else 0.0 for k, v in projected.items()
            },
            "realized_independent_archive_bytes": realized,
            "realized_independent_ratio": {
                k: v / raw if raw else 0.0 for k, v in realized.items()
            },
            "reset_penalty_bytes": reset_penalty,
            "extended_winner_counts": dict(sorted(winners.items())),
        }
        if dataset == "silesia":
            summary["strict_28_target_bytes"] = STRICT_28_MAX_BYTES
            summary["projected_gap_to_strict_28_overhead16"] = (
                projected["16"] - STRICT_28_MAX_BYTES
            )
            summary["would_project_below_28_overhead16"] = (
                projected["16"] <= STRICT_28_MAX_BYTES
            )
        out["segment_sizes"][key] = summary

    return out


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: exp120a_mixed_parent_grain_oracle.py <kephir2_native_k75_cli>"
        )
    cli = Path(sys.argv[1]).resolve()
    if not cli.is_file():
        raise SystemExit(f"CLI not found: {cli}")

    work = Path("exp120a_work")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    all_files = []
    dataset_rows = {"silesia": [], "external": []}
    index = 0

    for dataset, paths in dataset_files().items():
        for path in paths:
            whole = measure_whole_file(cli, dataset, path, work, index)
            whole["segments"] = {}
            for segment_bytes in SEGMENT_SIZES:
                measured = measure_segments(
                    cli,
                    path,
                    whole["exp118b_choice"],
                    whole["selected_outer_bytes"],
                    segment_bytes,
                    work,
                    index,
                )
                whole["segments"][str(segment_bytes // MiB)] = measured

            dataset_rows[dataset].append(whole)
            all_files.append(whole)
            print(
                "EXP120A_FILE",
                dataset,
                whole["file"],
                "RAW", whole["raw_bytes"],
                "EXP118B", whole["exp118b_choice"], whole["selected_archive_bytes"],
                "G4M", whole["segments"]["4"]["total_local_gain"],
                "G8M", whole["segments"]["8"]["total_local_gain"],
                "G16M", whole["segments"]["16"]["total_local_gain"],
                flush=True,
            )
            index += 1

    datasets = [
        summarize_dataset(name, dataset_rows[name], SEGMENT_SIZES)
        for name in ("silesia", "external")
    ]
    silesia = datasets[0]
    external = datasets[1]

    best = min(
        silesia["segment_sizes"].values(),
        key=lambda r: (r["projected_archive_bytes"]["16"], r["segment_mib"]),
    )

    result = {
        "experiment": "EXP-120A",
        "purpose": (
            "measure within-file local parent-grain value before changing K75 framing"
        ),
        "baseline_policy": "EXP-118B 2MiB stratified margin0",
        "base_candidates": list(BASE_CANDIDATES),
        "extended_candidates": list(CANDIDATES),
        "segment_sizes_bytes": SEGMENT_SIZES,
        "modeled_frame_overheads_bytes": FRAME_OVERHEADS,
        "strict_28_max_bytes": STRICT_28_MAX_BYTES,
        "datasets": datasets,
        "files": all_files,
        "best_silesia_projected_overhead16": best,
    }
    Path("exp120a_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(
        "EXP120A_SILESIA_BASELINE",
        silesia["exp118b_selected_bytes"],
        "RATIO", silesia["exp118b_selected_ratio"],
        flush=True,
    )
    print(
        "EXP120A_EXTERNAL_BASELINE",
        external["exp118b_selected_bytes"],
        "RATIO", external["exp118b_selected_ratio"],
        flush=True,
    )
    for key, summary in silesia["segment_sizes"].items():
        print(
            "EXP120A_SEGMENT",
            key + "MiB",
            "CHUNKS", summary["chunk_count"],
            "MIX_GAIN", summary["local_existing_mix_gain"],
            "G2_GAIN", summary["grain2_incremental_gain"],
            "TOTAL_LOCAL_GAIN", summary["total_local_gain"],
            "PROJECTED16", summary["projected_archive_bytes"]["16"],
            "PROJECTED_RATIO16", summary["projected_ratio"]["16"],
            "REALIZED16", summary["realized_independent_archive_bytes"]["16"],
            "RESET_PENALTY16", summary["reset_penalty_bytes"]["16"],
            "GAP28", summary["projected_gap_to_strict_28_overhead16"],
            "WINNERS", json.dumps(summary["extended_winner_counts"], sort_keys=True),
            flush=True,
        )
    print(
        "EXP120A_BEST",
        str(best["segment_mib"]) + "MiB",
        "PROJECTED16", best["projected_archive_bytes"]["16"],
        "RATIO", best["projected_ratio"]["16"],
        "GAP28", best["projected_gap_to_strict_28_overhead16"],
        "CLOSES28", int(best["would_project_below_28_overhead16"]),
        flush=True,
    )

    # Strong reproduction gates: EXP-120A must start from exactly the qualified
    # EXP-118B policy, otherwise all projected deltas would be misleading.
    if silesia["exp118b_selected_bytes"] != EXPECTED_EXP118B_SILESIA:
        raise RuntimeError(
            "EXP-118B Silesia baseline mismatch: "
            f"{silesia['exp118b_selected_bytes']} != {EXPECTED_EXP118B_SILESIA}"
        )
    if external["exp118b_selected_bytes"] != EXPECTED_EXP118B_EXTERNAL:
        raise RuntimeError(
            "EXP-118B external baseline mismatch: "
            f"{external['exp118b_selected_bytes']} != {EXPECTED_EXP118B_EXTERNAL}"
        )

    shutil.rmtree(work, ignore_errors=True)
    print("EXP120A_VALIDATION_PASS", flush=True)


if __name__ == "__main__":
    main()
