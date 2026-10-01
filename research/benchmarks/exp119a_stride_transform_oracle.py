#!/usr/bin/env python3
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

MiB = 1024 * 1024
EXISTING = {0, 2, 4, 16, 1024}
EXTENDED = {0, 2, 4, 16, 256, 512, 1024, 2048, 4096}


def run_helper(helper, path, chunk_kib=512):
    p = subprocess.run(
        [str(helper), str(path), str(chunk_kib)],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = {}
    summary = {}
    for line in p.stdout.splitlines():
        if line.startswith("LAG="):
            parts = line.split()
            kv = dict(x.split("=", 1) for x in parts)
            lag = int(kv["LAG"])
            rows[lag] = {
                "bytes": int(kv["BYTES"]),
                "encode_seconds": float(kv["ENC_SECONDS"]),
                "decode_seconds": float(kv["DEC_SECONDS"]),
                "sha_ok": kv["SHA_OK"] == "1",
            }
        elif "=" in line:
            k, v = line.split("=", 1)
            summary[k] = v
    return rows, summary


def make_raster(width, size, seed, noise):
    rng = random.Random(seed)
    rows = size // width
    row = bytearray(rng.randrange(256) for _ in range(width))
    out = bytearray(row)
    for r in range(1, rows):
        nxt = bytearray(width)
        bias = ((r // 7) % 9) - 4
        for x, v in enumerate(row):
            horizontal = row[x - 1] if x else v
            predictor = (3 * v + horizontal) // 4
            nxt[x] = (predictor + bias + rng.randrange(-noise, noise + 1)) & 255
        out.extend(nxt)
        row = nxt
    return bytes(out[:size])


def build_rasters(root):
    root.mkdir(parents=True, exist_ok=True)
    specs = [
        (256, 4 * MiB, 11901, 2),
        (512, 4 * MiB, 11902, 2),
        (1024, 4 * MiB, 11903, 2),
        (2048, 4 * MiB, 11904, 2),
        (4096, 4 * MiB, 11905, 2),
    ]
    paths = []
    for width, size, seed, noise in specs:
        path = root / f"raster_w{width}.bin"
        path.write_bytes(make_raster(width, size, seed, noise))
        paths.append(path)
    return paths


def measure(helper, dataset, path):
    rows, summary = run_helper(helper, path)
    if set(rows) != EXTENDED:
        raise RuntimeError(f"missing lag result for {path}: {sorted(rows)}")
    if not all(v["sha_ok"] for v in rows.values()):
        raise RuntimeError(f"roundtrip failure for {path}")

    existing_lag = min(EXISTING, key=lambda lag: (rows[lag]["bytes"], lag))
    extended_lag = min(EXTENDED, key=lambda lag: (rows[lag]["bytes"], lag))
    result = {
        "dataset": dataset,
        "file": path.name,
        "raw_bytes": int(summary["RAW_BYTES"]),
        "chunk_bytes": int(summary["CHUNK_BYTES"]),
        "lags": {str(k): rows[k] for k in sorted(rows)},
        "existing_best_lag": existing_lag,
        "existing_best_bytes": rows[existing_lag]["bytes"],
        "extended_best_lag": extended_lag,
        "extended_best_bytes": rows[extended_lag]["bytes"],
        "gain_from_new_strides": rows[existing_lag]["bytes"] - rows[extended_lag]["bytes"],
    }
    print(
        "EXP119A_FILE", dataset, path.name,
        "RAW", result["raw_bytes"],
        "EXISTING", existing_lag, result["existing_best_bytes"],
        "EXTENDED", extended_lag, result["extended_best_bytes"],
        "GAIN", result["gain_from_new_strides"],
        flush=True,
    )
    return result


def summarize(dataset, rows):
    subset = [r for r in rows if r["dataset"] == dataset]
    raw = sum(r["raw_bytes"] for r in subset)
    existing = sum(r["existing_best_bytes"] for r in subset)
    extended = sum(r["extended_best_bytes"] for r in subset)
    wins = {}
    for r in subset:
        lag = str(r["extended_best_lag"])
        wins[lag] = wins.get(lag, 0) + 1
    return {
        "dataset": dataset,
        "file_count": len(subset),
        "raw_bytes": raw,
        "existing_oracle_bytes": existing,
        "extended_oracle_bytes": extended,
        "new_stride_gain_bytes": existing - extended,
        "existing_ratio": existing / raw,
        "extended_ratio": extended / raw,
        "extended_winner_counts": dict(sorted(wins.items(), key=lambda kv: int(kv[0]))),
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp119a_stride_transform_oracle.py <helper>")
    helper = Path(sys.argv[1]).resolve()
    if not helper.is_file():
        raise SystemExit(f"helper not found: {helper}")

    rows = []
    for path in sorted(Path("corpora/silesia").glob("*")):
        if path.is_file():
            rows.append(measure(helper, "silesia", path))

    raster_root = Path("exp119a_rasters")
    shutil.rmtree(raster_root, ignore_errors=True)
    for path in build_rasters(raster_root):
        rows.append(measure(helper, "raster_holdout", path))

    silesia = summarize("silesia", rows)
    raster = summarize("raster_holdout", rows)
    result = {
        "experiment": "EXP-119A",
        "purpose": "measure reversible Delta+Transpose stride potential before changing K75 format",
        "chunk_kib": 512,
        "existing_lags": sorted(EXISTING),
        "extended_lags": sorted(EXTENDED),
        "datasets": [silesia, raster],
        "files": rows,
    }
    Path("exp119a_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))

    print(
        "EXP119A_DATASET silesia",
        "EXISTING", silesia["existing_oracle_bytes"],
        "EXTENDED", silesia["extended_oracle_bytes"],
        "GAIN", silesia["new_stride_gain_bytes"],
        "WINNERS", json.dumps(silesia["extended_winner_counts"], sort_keys=True),
        flush=True,
    )
    print(
        "EXP119A_DATASET raster_holdout",
        "EXISTING", raster["existing_oracle_bytes"],
        "EXTENDED", raster["extended_oracle_bytes"],
        "GAIN", raster["new_stride_gain_bytes"],
        "WINNERS", json.dumps(raster["extended_winner_counts"], sort_keys=True),
        flush=True,
    )
    print("EXP119A_COMPLETE", flush=True)

    shutil.rmtree(raster_root, ignore_errors=True)


if __name__ == "__main__":
    main()
