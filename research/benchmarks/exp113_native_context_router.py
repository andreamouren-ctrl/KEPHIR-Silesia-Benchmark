#!/usr/bin/env python3
"""
EXP-113 — Native Adaptive Context Router Qualification

Research-only.

Validates the C++ bounded-sampling context policy introduced after EXP-112.

For every file it measures:
- current baseline;
- explicit 4 MiB parent/context with adaptive grain;
- explicit 8 MiB parent/context with adaptive grain;
- native adaptive-context flag.

The adaptive archive is compared byte-for-byte (SHA-256) with the explicit
reference archives, so context decisions are inferred without exposing
research policy details through the public ABI.

Datasets:
- canonical Silesia;
- deterministic EXP-112 holdout.

No production default is changed.
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exp112_adaptive_context_router as E112

BASELINE = "baseline"
CTX4 = "ctx4m"
CTX8 = "ctx8m"
ADAPTIVE = "adaptive"

CONFIGS = {
    BASELINE: [],
    CTX4: ["4096", "4096", "0"],
    CTX8: ["8192", "8192", "0"],
    ADAPTIVE: ["adaptive"],
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_cli(text):
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def run_one(cli, src, work, dataset, logical_name, label):
    safe = dataset.replace("/", "_")
    arc = work / f"{safe}_{logical_name}_{label}.kpf"
    out = work / f"out_{safe}_{logical_name}_{label}"

    cmd = [str(cli), "c", str(src), str(arc), "1"] + CONFIGS[label]
    cp = subprocess.run(
        cmd, check=True, text=True, capture_output=True
    )
    cm = parse_cli(cp.stdout)

    if out.exists():
        shutil.rmtree(out)
    dp = subprocess.run(
        [str(cli), "d", str(arc), str(out), "1"],
        check=True, text=True, capture_output=True
    )
    dm = parse_cli(dp.stdout)

    restored = out / src.name
    if not restored.is_file() or sha256(restored) != sha256(src):
        raise SystemExit(
            f"SHA mismatch dataset={dataset} file={logical_name} cfg={label}"
        )

    result = {
        "archive_bytes": arc.stat().st_size,
        "archive_sha256": sha256(arc),
        "comp_seconds": float(cm["SECONDS"]),
        "dec_seconds": float(dm["SECONDS"]),
        "sha_pass": True,
        "adaptive_flag": int(cm.get("ADAPTIVE_CONTEXT", "0")),
    }

    shutil.rmtree(out)
    arc.unlink()
    return result


def evaluate(cli, work, dataset, files):
    rows = []

    for logical_name, src in files.items():
        features = E112.cheap_features(src)
        expected = E112.route_spread_v1(features)

        measured = {
            label: run_one(
                cli, src, work, dataset, logical_name, label
            )
            for label in (BASELINE, CTX4, CTX8, ADAPTIVE)
        }

        refs = (BASELINE, CTX4, CTX8)
        oracle = min(
            refs,
            key=lambda label: (
                measured[label]["archive_bytes"],
                refs.index(label),
            ),
        )

        adaptive_hash = measured[ADAPTIVE]["archive_sha256"]
        matches = [
            label for label in refs
            if measured[label]["archive_sha256"] == adaptive_hash
        ]

        row = {
            "file": logical_name,
            "features": features,
            "expected_spread_v1": expected,
            "oracle": oracle,
            "adaptive_matches": matches,
            "measured": measured,
            "adaptive_regret": (
                measured[ADAPTIVE]["archive_bytes"]
                - measured[oracle]["archive_bytes"]
            ),
            "adaptive_delta_vs_baseline": (
                measured[ADAPTIVE]["archive_bytes"]
                - measured[BASELINE]["archive_bytes"]
            ),
        }
        rows.append(row)

        print(
            "EXP113_FILE",
            dataset,
            logical_name,
            "EXPECTED", expected,
            "ORACLE", oracle,
            "MATCH", ",".join(matches) if matches else "NONE",
            "DELTA_BASE", row["adaptive_delta_vs_baseline"],
            "REGRET", row["adaptive_regret"],
            flush=True,
        )

    raw_total = sum(r["features"]["raw_bytes"] for r in rows)
    baseline_total = sum(
        r["measured"][BASELINE]["archive_bytes"] for r in rows
    )
    adaptive_total = sum(
        r["measured"][ADAPTIVE]["archive_bytes"] for r in rows
    )
    oracle_total = sum(
        r["measured"][r["oracle"]]["archive_bytes"] for r in rows
    )

    adaptive_comp = sum(
        r["measured"][ADAPTIVE]["comp_seconds"] for r in rows
    )
    adaptive_dec = sum(
        r["measured"][ADAPTIVE]["dec_seconds"] for r in rows
    )

    exact_expected = sum(
        1 for r in rows
        if r["expected_spread_v1"] in r["adaptive_matches"]
    )
    harmful = [
        {
            "file": r["file"],
            "delta_vs_baseline": r["adaptive_delta_vs_baseline"],
            "expected": r["expected_spread_v1"],
            "matches": r["adaptive_matches"],
        }
        for r in rows
        if r["adaptive_delta_vs_baseline"] > 0
    ]

    result = {
        "dataset": dataset,
        "raw_bytes": raw_total,
        "baseline_bytes": baseline_total,
        "adaptive_bytes": adaptive_total,
        "adaptive_ratio": adaptive_total / raw_total,
        "gain_vs_baseline": baseline_total - adaptive_total,
        "oracle_bytes": oracle_total,
        "regret_vs_oracle": adaptive_total - oracle_total,
        "policy_match_count": exact_expected,
        "file_count": len(rows),
        "harmful_selections": harmful,
        "adaptive_comp_MBps": raw_total / 1e6 / adaptive_comp,
        "adaptive_dec_MBps": raw_total / 1e6 / adaptive_dec,
        "files": rows,
    }

    print(
        "EXP113_DATASET",
        dataset,
        "BASE", baseline_total,
        "ADAPTIVE", adaptive_total,
        "ORACLE", oracle_total,
        "GAIN", result["gain_vs_baseline"],
        "REGRET", result["regret_vs_oracle"],
        "MATCH", f"{exact_expected}/{len(rows)}",
        "HARM", len(harmful),
        "COMP_MBPS", result["adaptive_comp_MBps"],
        "DEC_MBPS", result["adaptive_dec_MBps"],
        flush=True,
    )
    return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: exp113_native_context_router.py NATIVE_K75_CLI"
        )

    cli = Path(sys.argv[1]).resolve()
    corpus = ROOT / "corpora" / "silesia"
    work = ROOT / "exp113_native_context_router"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia = {
        name: corpus / name
        for name in E112.SILESIA_FILES
    }
    holdout = E112.make_holdout(work / "holdout")

    datasets = [
        evaluate(cli, work, "silesia", silesia),
        evaluate(cli, work, "holdout", holdout),
    ]

    result = {
        "experiment": "EXP-113",
        "purpose": "native-bounded-adaptive-context-router",
        "sample_budget_max_bytes_per_stream": 256 * 1024,
        "datasets": datasets,
    }

    Path("exp113_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )

    assert datasets[0]["raw_bytes"] == 211938580
    assert all(
        m["sha_pass"]
        for ds in datasets
        for row in ds["files"]
        for m in row["measured"].values()
    )
    assert all(
        row["measured"][ADAPTIVE]["adaptive_flag"] == 1
        for ds in datasets
        for row in ds["files"]
    )

    print(
        "EXP113_COMPLETE",
        "SILESIA_GAIN", datasets[0]["gain_vs_baseline"],
        "SILESIA_REGRET", datasets[0]["regret_vs_oracle"],
        "HOLDOUT_GAIN", datasets[1]["gain_vs_baseline"],
        "HOLDOUT_REGRET", datasets[1]["regret_vs_oracle"],
        flush=True,
    )


if __name__ == "__main__":
    main()
