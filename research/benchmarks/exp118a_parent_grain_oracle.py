#!/usr/bin/env python3
import hashlib
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

MiB = 1024 * 1024

CANDIDATES = {
    "baseline": [],
    "ctx4": ["4096", "4096", "0"],
    "ctx8": ["8192", "8192", "0"],
    "grain4": ["4096", "4096", "1"],
    "grain8": ["8192", "8192", "1"],
}
CONTEXT_ONLY = ("baseline", "ctx4", "ctx8")


def run(cmd):
    p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    out = {}
    for line in p.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def entropy(data):
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def stride_sample(data, n=4096):
    if len(data) <= n:
        return data
    step = max(1, len(data) // n)
    return data[::step][:n]


def cheap_features(path):
    data = path.read_bytes()
    n = len(data)
    if not data:
        return {"bytes": 0, "entropy": 0.0, "quarter_entropy_spread": 0.0}
    q = max(1, n // 4)
    hs = []
    for i in range(4):
        lo = i * q
        hi = n if i == 3 else min(n, (i + 1) * q)
        hs.append(entropy(stride_sample(data[lo:hi])))
    return {
        "bytes": n,
        "entropy": entropy(stride_sample(data, 16384)),
        "quarter_entropy_spread": max(hs) - min(hs),
        "quarter_entropies": hs,
    }


def dataset_files():
    silesia = sorted(p for p in Path("corpora/silesia").rglob("*") if p.is_file())
    external = []
    for root_name in ("canterbury", "calgary", "large"):
        root = Path("corpora") / root_name
        external.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    return {"silesia": silesia, "external": external}


def file_id(dataset, path):
    if dataset == "silesia":
        return path.name
    return str(path.relative_to("corpora"))


def measure_file(cli, dataset, path, work, index):
    features = cheap_features(path)
    source_sha = sha256(path)
    rows = {}

    for name, extra in CANDIDATES.items():
        archive = work / f"{index:03d}_{name}.kpf"
        restored = work / f"{index:03d}_{name}_out"
        if restored.exists():
            shutil.rmtree(restored)

        enc = run([str(cli), "c", str(path), str(archive), "4", *extra])
        dec = run([str(cli), "d", str(archive), str(restored), "4"])
        restored_file = restored / path.name
        ok = restored_file.is_file() and sha256(restored_file) == source_sha
        if not ok:
            raise RuntimeError(f"roundtrip failed: {dataset}/{file_id(dataset, path)} {name}")

        rows[name] = {
            "bytes": int(enc["OUTPUT_BYTES"]),
            "compress_seconds": float(enc["SECONDS"]),
            "decompress_seconds": float(dec["SECONDS"]),
            "sha_ok": True,
        }
        archive.unlink(missing_ok=True)
        shutil.rmtree(restored, ignore_errors=True)

    context_best = min(CONTEXT_ONLY, key=lambda k: (rows[k]["bytes"], k))
    oracle = min(CANDIDATES, key=lambda k: (rows[k]["bytes"], k))
    base = rows["baseline"]["bytes"]
    context_bytes = rows[context_best]["bytes"]
    oracle_bytes = rows[oracle]["bytes"]

    result = {
        "dataset": dataset,
        "file": file_id(dataset, path),
        "raw_bytes": path.stat().st_size,
        "features": features,
        "candidates": rows,
        "context_oracle": context_best,
        "context_oracle_bytes": context_bytes,
        "oracle": oracle,
        "oracle_bytes": oracle_bytes,
        "context_gain_vs_baseline": base - context_bytes,
        "grain_gain_vs_context_oracle": context_bytes - oracle_bytes,
        "total_gain_vs_baseline": base - oracle_bytes,
    }
    print(
        "EXP118A_FILE", dataset, result["file"],
        "RAW", result["raw_bytes"],
        "BASE", base,
        "CTX", context_best, context_bytes,
        "ORACLE", oracle, oracle_bytes,
        "GRAIN_GAIN", result["grain_gain_vs_context_oracle"],
        "SHA", 1,
        flush=True,
    )
    return result


def summarize(dataset, rows):
    raw = sum(r["raw_bytes"] for r in rows)
    totals = {
        c: sum(r["candidates"][c]["bytes"] for r in rows)
        for c in CANDIDATES
    }
    comp_seconds = {
        c: sum(r["candidates"][c]["compress_seconds"] for r in rows)
        for c in CANDIDATES
    }
    dec_seconds = {
        c: sum(r["candidates"][c]["decompress_seconds"] for r in rows)
        for c in CANDIDATES
    }
    context_oracle_bytes = sum(r["context_oracle_bytes"] for r in rows)
    oracle_bytes = sum(r["oracle_bytes"] for r in rows)
    winners = Counter(r["oracle"] for r in rows)
    context_winners = Counter(r["context_oracle"] for r in rows)

    out = {
        "dataset": dataset,
        "file_count": len(rows),
        "raw_bytes": raw,
        "candidate_bytes": totals,
        "candidate_ratio": {c: totals[c] / raw for c in CANDIDATES},
        "compress_seconds": comp_seconds,
        "decompress_seconds": dec_seconds,
        "context_oracle_bytes": context_oracle_bytes,
        "context_oracle_ratio": context_oracle_bytes / raw,
        "full_oracle_bytes": oracle_bytes,
        "full_oracle_ratio": oracle_bytes / raw,
        "grain_gain_vs_context_oracle": context_oracle_bytes - oracle_bytes,
        "total_gain_vs_baseline": totals["baseline"] - oracle_bytes,
        "winner_counts": dict(sorted(winners.items())),
        "context_winner_counts": dict(sorted(context_winners.items())),
    }
    print(
        "EXP118A_DATASET", dataset,
        "RAW", raw,
        "BASE", totals["baseline"],
        "CTX_ORACLE", context_oracle_bytes,
        "FULL_ORACLE", oracle_bytes,
        "RATIO", oracle_bytes / raw,
        "GRAIN_GAIN", context_oracle_bytes - oracle_bytes,
        "WINNERS", json.dumps(out["winner_counts"], sort_keys=True),
        flush=True,
    )
    return out


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp118a_parent_grain_oracle.py <kephir2_native_k75_cli>")
    cli = Path(sys.argv[1]).resolve()
    if not cli.is_file():
        raise SystemExit(f"CLI not found: {cli}")

    work = Path("exp118a_work")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    all_rows = []
    summaries = []
    index = 0
    for dataset, files in dataset_files().items():
        rows = []
        for path in files:
            row = measure_file(cli, dataset, path, work, index)
            rows.append(row)
            all_rows.append(row)
            index += 1
        summaries.append(summarize(dataset, rows))

    result = {
        "experiment": "EXP-118A",
        "purpose": "measure per-file parent-grain oracle before deriving a router",
        "candidates": list(CANDIDATES),
        "datasets": summaries,
        "files": all_rows,
    }
    Path("exp118a_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    shutil.rmtree(work, ignore_errors=True)
    print("EXP118A_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
