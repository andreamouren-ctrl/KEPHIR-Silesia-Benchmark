#!/usr/bin/env python3
"""
EXP-111 — Adaptive Inner Context Candidate

Research-only.

EXP-110 proved that most of the ratio gain comes from a larger inner AUR2
context, while enlarging the K75 parent with the inner context fixed at
512 KiB is not useful.

This experiment asks the production question that EXP-110 did not answer:
can K75 keep adaptive grain selection while using a larger parent window and
therefore expose longer AUR2 contexts only where the content remains coherent?

No production default is changed.  Every archive is decoded by the ordinary
decoder and SHA-256 verified.

Rows:
- current production baseline;
- 4 MiB parent with adaptive grain and 512 KiB .. 4 MiB inner context;
- 8 MiB parent with adaptive grain and 512 KiB / 4 MiB / 8 MiB inner context.

The result also reports a per-file oracle.  That oracle is NOT a production
policy; it is the upper bound for a later cheap content gate.
"""
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import sys

ROOT = Path.cwd()
FILES = [
    "dickens", "mozilla", "mr", "nci", "ooffice", "osdb",
    "reymont", "samba", "sao", "webster", "x-ray", "xml",
]

CONFIGS = [
    {"label": "baseline-adaptive", "parent_kib": 0, "inner_kib": 0, "force": 0},
    {"label": "p4096-i512-adaptive", "parent_kib": 4096, "inner_kib": 512, "force": 0},
    {"label": "p4096-i1024-adaptive", "parent_kib": 4096, "inner_kib": 1024, "force": 0},
    {"label": "p4096-i2048-adaptive", "parent_kib": 4096, "inner_kib": 2048, "force": 0},
    {"label": "p4096-i4096-adaptive", "parent_kib": 4096, "inner_kib": 4096, "force": 0},
    {"label": "p8192-i512-adaptive", "parent_kib": 8192, "inner_kib": 512, "force": 0},
    {"label": "p8192-i4096-adaptive", "parent_kib": 8192, "inner_kib": 4096, "force": 0},
    {"label": "p8192-i8192-adaptive", "parent_kib": 8192, "inner_kib": 8192, "force": 0},
]


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


def entropy(data):
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    h = 0.0
    for count in counts:
        if count:
            p = count / n
            h -= p * math.log2(p)
    return h


def stride_sample(data, target=8192):
    if not data:
        return b""
    step = max(1, len(data) // target)
    return data[::step]


def cheap_features(path):
    data = path.read_bytes()
    sample = stride_sample(data)
    n = max(1, len(sample))
    printable = sum(
        1 for b in sample
        if b in (9, 10, 13) or 32 <= b < 127
    ) / n
    zeros = sample.count(0) / n

    quarter_entropy = []
    if data:
        q = max(1, len(data) // 4)
        for i in range(4):
            start = i * q
            end = len(data) if i == 3 else min(len(data), (i + 1) * q)
            quarter_entropy.append(entropy(stride_sample(data[start:end], 4096)))

    spread = (
        max(quarter_entropy) - min(quarter_entropy)
        if quarter_entropy else 0.0
    )

    return {
        "raw_bytes": len(data),
        "sample_entropy": entropy(sample),
        "sample_printable_fraction": printable,
        "sample_zero_fraction": zeros,
        "quarter_entropy_spread": spread,
        "text_like": printable >= 0.88,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: exp111_adaptive_inner_context.py NATIVE_K75_CLI"
        )

    cli = Path(sys.argv[1]).resolve()
    corpus = ROOT / "corpora" / "silesia"
    work = ROOT / "exp111_adaptive_inner_context"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    features = {
        name: cheap_features(corpus / name)
        for name in FILES
    }

    rows = []

    for cfg in CONFIGS:
        raw_total = 0
        archive_total = 0
        comp_total = 0.0
        dec_total = 0.0
        per_file = []

        for name in FILES:
            src = corpus / name
            arc = work / f"{name}.{cfg['label']}.kpf"
            out = work / f"out_{cfg['label']}_{name}"

            cmd = [str(cli), "c", str(src), str(arc), "1"]
            if cfg["parent_kib"]:
                cmd += [
                    str(cfg["parent_kib"]),
                    str(cfg["inner_kib"]),
                    str(cfg["force"]),
                ]

            cp = subprocess.run(
                cmd, check=True, text=True, capture_output=True
            )
            cm = parse_cli(cp.stdout)
            comp = float(cm["SECONDS"])

            if out.exists():
                shutil.rmtree(out)
            dp = subprocess.run(
                [str(cli), "d", str(arc), str(out), "1"],
                check=True, text=True, capture_output=True
            )
            dm = parse_cli(dp.stdout)
            dec = float(dm["SECONDS"])

            restored = out / name
            if not restored.is_file() or sha256(restored) != sha256(src):
                raise SystemExit(
                    f"SHA mismatch config={cfg['label']} file={name}"
                )

            raw = src.stat().st_size
            ab = arc.stat().st_size
            raw_total += raw
            archive_total += ab
            comp_total += comp
            dec_total += dec

            per_file.append({
                "file": name,
                "raw_bytes": raw,
                "archive_bytes": ab,
                "ratio": ab / raw,
                "comp_seconds": comp,
                "dec_seconds": dec,
                "features": features[name],
            })
            shutil.rmtree(out)

        row = {
            **cfg,
            "raw_bytes": raw_total,
            "archive_bytes": archive_total,
            "ratio": archive_total / raw_total,
            "comp_seconds": comp_total,
            "dec_seconds": dec_total,
            "comp_MBps": raw_total / 1e6 / comp_total,
            "dec_MBps": raw_total / 1e6 / dec_total,
            "sha_all_pass": True,
            "per_file": per_file,
        }
        rows.append(row)

        print(
            "EXP111_ROW",
            "LABEL", cfg["label"],
            "PARENT_KIB", cfg["parent_kib"],
            "INNER_KIB", cfg["inner_kib"],
            "BYTES", archive_total,
            "RATIO", row["ratio"],
            "COMP_MBPS", row["comp_MBps"],
            "DEC_MBPS", row["dec_MBps"],
            "SHA", True,
            flush=True,
        )

    baseline = rows[0]
    baseline_by_file = {
        item["file"]: item
        for item in baseline["per_file"]
    }

    for row in rows:
        row["bytes_vs_baseline"] = (
            row["archive_bytes"] - baseline["archive_bytes"]
        )
        row["ratio_delta_vs_baseline"] = row["ratio"] - baseline["ratio"]

    oracle_files = []
    oracle_total = 0
    baseline_total = baseline["archive_bytes"]

    for name in FILES:
        candidates = []
        for row in rows:
            item = next(x for x in row["per_file"] if x["file"] == name)
            candidates.append({
                "label": row["label"],
                "parent_kib": row["parent_kib"],
                "inner_kib": row["inner_kib"],
                "archive_bytes": item["archive_bytes"],
                "comp_seconds": item["comp_seconds"],
                "dec_seconds": item["dec_seconds"],
            })

        best = min(candidates, key=lambda x: x["archive_bytes"])
        base = baseline_by_file[name]
        oracle_total += best["archive_bytes"]
        oracle_files.append({
            "file": name,
            "features": features[name],
            "baseline_bytes": base["archive_bytes"],
            "best": best,
            "gain_vs_baseline": base["archive_bytes"] - best["archive_bytes"],
            "candidates": candidates,
        })
        print(
            "EXP111_ORACLE",
            "FILE", name,
            "BEST", best["label"],
            "BYTES", best["archive_bytes"],
            "GAIN", base["archive_bytes"] - best["archive_bytes"],
            flush=True,
        )

    result = {
        "experiment": "EXP-111",
        "purpose": "adaptive-inner-context-candidate-with-adaptive-grain",
        "note": (
            "Per-file oracle is an upper bound only; no production policy "
            "is promoted by this diagnostic."
        ),
        "rows": rows,
        "oracle": {
            "archive_bytes": oracle_total,
            "ratio": oracle_total / baseline["raw_bytes"],
            "gain_vs_baseline": baseline_total - oracle_total,
            "per_file": oracle_files,
        },
    }

    Path("exp111_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )

    assert all(r["raw_bytes"] == 211938580 for r in rows)
    assert all(r["sha_all_pass"] for r in rows)

    print(
        "EXP111_COMPLETE",
        "BASE", baseline_total,
        "ORACLE", oracle_total,
        "ORACLE_GAIN", baseline_total - oracle_total,
        flush=True,
    )


if __name__ == "__main__":
    main()
