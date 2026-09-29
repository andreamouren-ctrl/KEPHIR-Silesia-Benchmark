#!/usr/bin/env python3
"""
EXP-112 — Long-Context Gate Holdout

The candidate gate is frozen from EXP-111 before this holdout:

    size >= 4 MiB
    AND quarter_entropy_spread < 0.20
        printable >= 0.95 and zero <= 0.01 -> 8 MiB / 8 MiB
        otherwise                           -> 4 MiB / 4 MiB
    else -> production baseline

This file intentionally contains unseen deterministic workloads, including
counterexamples where entropy is stationary but byte distributions change.

The gate is compared against an exact configuration oracle.  No production
code is changed by this experiment.
"""
from pathlib import Path
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys

ROOT = Path.cwd()
MiB = 1024 * 1024

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
BY_LABEL = {c["label"]: c for c in CONFIGS}


def repeat_to(pattern, size):
    q, r = divmod(size, len(pattern))
    return pattern * q + pattern[:r]


def make_holdout(root):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    prose = (
        b"ordinary language carries repeated words and local context while "
        b"remaining stable across a long document.\n"
    )
    code = (
        b"int transform(int x){return (x*31)+7;} "
        b"struct Row{int a;int b;int c;};\n"
    )
    record = (
        b"id=000001|state=active|region=eu|value=000042|"
        b"timestamp=2026-09-29\n"
    )
    zero = b"\x00" * 32 + b"\xff" * 32 + bytes(range(32))

    rng = random.Random(11200)
    random8 = rng.randbytes(8 * MiB)
    random_block = random.Random(11201).randbytes(64 * 1024)

    files = {}
    files["stable_prose"] = repeat_to(prose, 8 * MiB)
    files["stable_code"] = repeat_to(code, 8 * MiB)
    files["stable_records"] = repeat_to(record, 8 * MiB)
    files["stable_zero"] = repeat_to(zero, 8 * MiB)
    files["random_stationary"] = random8
    files["repeated_random_block"] = repeat_to(random_block, 8 * MiB)

    q = 2 * MiB
    files["quarter_mixed"] = (
        repeat_to(prose, q)
        + repeat_to(code, q)
        + repeat_to(zero, q)
        + random.Random(11202).randbytes(q)
    )
    files["entropy_shift"] = (
        b"A" * q
        + random.Random(11203).randbytes(q)
        + repeat_to(bytes(range(16)), q)
        + random.Random(11204).randbytes(q)
    )

    # Same approximate entropy per quarter, different symbol supports.
    equal_entropy = []
    for base in (0, 64, 128, 192):
        alphabet = bytes((base + i) & 255 for i in range(64))
        equal_entropy.append(repeat_to(alphabet, q))
    files["distribution_shift_equal_entropy"] = b"".join(equal_entropy)

    topics = [
        b"alpha beta gamma delta epsilon zeta eta theta words words words\n",
        b"river mountain forest ocean valley cloud rain wind story story\n",
        b"database table query index record column row value data data data\n",
        b"engine parser model context stream archive byte code code code\n",
    ]
    files["text_topic_shift"] = b"".join(
        repeat_to(topic, q) for topic in topics
    )

    files["numeric_le"] = repeat_to(
        b"\x01\x00\x00\x00\x02\x00\x00\x00"
        b"\x03\x00\x00\x00\x04\x00\x00\x00",
        8 * MiB,
    )
    files["sawtooth_256"] = repeat_to(bytes(range(256)), 8 * MiB)
    files["base64_stationary"] = repeat_to(
        b"QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo"
        b"YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=\n",
        8 * MiB,
    )

    blocks = []
    for i in range(64):
        if i % 2 == 0:
            blocks.append(repeat_to(prose, 128 * 1024))
        else:
            blocks.append(random.Random(11300 + i).randbytes(128 * 1024))
    files["alternating_128k"] = b"".join(blocks)

    files["small_text"] = repeat_to(prose, 1 * MiB)
    files["small_random"] = random.Random(11400).randbytes(1 * MiB)

    paths = {}
    for name, data in files.items():
        path = root / f"{name}.dat"
        path.write_bytes(data)
        paths[name] = path
    return paths


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(MiB), b""):
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
            quarter_entropy.append(
                entropy(stride_sample(data[start:end], 4096))
            )

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
    }


def choose_candidate(features):
    if (
        features["raw_bytes"] >= 4 * MiB
        and features["quarter_entropy_spread"] < 0.20
    ):
        if (
            features["sample_printable_fraction"] >= 0.95
            and features["sample_zero_fraction"] <= 0.01
        ):
            return "p8192-i8192-adaptive"
        return "p4096-i4096-adaptive"
    return "baseline-adaptive"


def run_config(cli, src, cfg, work, name):
    arc = work / f"{name}.{cfg['label']}.kpf"
    out = work / f"out_{name}_{cfg['label']}"

    cmd = [str(cli), "c", str(src), str(arc), "1"]
    if cfg["parent_kib"]:
        cmd += [
            str(cfg["parent_kib"]),
            str(cfg["inner_kib"]),
            str(cfg["force"]),
        ]

    cp = subprocess.run(cmd, check=True, text=True, capture_output=True)
    cm = parse_cli(cp.stdout)

    if out.exists():
        shutil.rmtree(out)
    dp = subprocess.run(
        [str(cli), "d", str(arc), str(out), "1"],
        check=True, text=True, capture_output=True,
    )
    dm = parse_cli(dp.stdout)

    restored = out / src.name
    ok = restored.is_file() and sha256(restored) == sha256(src)
    if not ok:
        raise SystemExit(
            f"SHA mismatch holdout={name} config={cfg['label']}"
        )

    result = {
        "label": cfg["label"],
        "archive_bytes": arc.stat().st_size,
        "comp_seconds": float(cm["SECONDS"]),
        "dec_seconds": float(dm["SECONDS"]),
        "sha": True,
    }

    shutil.rmtree(out)
    arc.unlink()
    return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: exp112_long_context_holdout.py NATIVE_K75_CLI"
        )

    cli = Path(sys.argv[1]).resolve()
    input_root = ROOT / "exp112_holdout_inputs"
    work = ROOT / "exp112_holdout_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    paths = make_holdout(input_root)

    rows = []
    total_baseline = 0
    total_selected = 0
    total_oracle = 0
    total_regret = 0
    selected_regression = 0
    correct = 0

    for name, src in paths.items():
        features = cheap_features(src)
        selected_label = choose_candidate(features)

        candidates = [
            run_config(cli, src, cfg, work, name)
            for cfg in CONFIGS
        ]
        by_label = {x["label"]: x for x in candidates}
        baseline = by_label["baseline-adaptive"]
        selected = by_label[selected_label]
        oracle = min(candidates, key=lambda x: x["archive_bytes"])

        regret = selected["archive_bytes"] - oracle["archive_bytes"]
        regression = selected["archive_bytes"] - baseline["archive_bytes"]

        total_baseline += baseline["archive_bytes"]
        total_selected += selected["archive_bytes"]
        total_oracle += oracle["archive_bytes"]
        total_regret += regret
        selected_regression += max(0, regression)
        correct += selected_label == oracle["label"]

        row = {
            "name": name,
            "features": features,
            "selected": selected_label,
            "oracle": oracle["label"],
            "baseline_bytes": baseline["archive_bytes"],
            "selected_bytes": selected["archive_bytes"],
            "oracle_bytes": oracle["archive_bytes"],
            "regret_bytes": regret,
            "regression_vs_baseline": regression,
            "candidates": candidates,
        }
        rows.append(row)

        print(
            "EXP112_CASE",
            "NAME", name,
            "SPREAD", features["quarter_entropy_spread"],
            "PRINT", features["sample_printable_fraction"],
            "ZERO", features["sample_zero_fraction"],
            "SELECTED", selected_label,
            "ORACLE", oracle["label"],
            "REGRET", regret,
            "VS_BASE", regression,
            flush=True,
        )

    result = {
        "experiment": "EXP-112",
        "candidate_gate": {
            "min_bytes": 4 * MiB,
            "quarter_entropy_spread_lt": 0.20,
            "text_printable_ge": 0.95,
            "text_zero_le": 0.01,
            "text_choice": "p8192-i8192-adaptive",
            "other_choice": "p4096-i4096-adaptive",
            "fallback": "baseline-adaptive",
        },
        "summary": {
            "cases": len(rows),
            "exact_oracle_matches": correct,
            "baseline_bytes": total_baseline,
            "selected_bytes": total_selected,
            "oracle_bytes": total_oracle,
            "gain_vs_baseline": total_baseline - total_selected,
            "oracle_gain_vs_baseline": total_baseline - total_oracle,
            "total_regret_bytes": total_regret,
            "positive_regression_bytes": selected_regression,
        },
        "rows": rows,
    }

    Path("exp112_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )

    assert all(
        all(c["sha"] for c in row["candidates"])
        for row in rows
    )

    s = result["summary"]
    print(
        "EXP112_COMPLETE",
        "CASES", s["cases"],
        "EXACT", s["exact_oracle_matches"],
        "BASE", s["baseline_bytes"],
        "SELECTED", s["selected_bytes"],
        "ORACLE", s["oracle_bytes"],
        "GAIN", s["gain_vs_baseline"],
        "REGRET", s["total_regret_bytes"],
        "POSITIVE_REGRESSION", s["positive_regression_bytes"],
        flush=True,
    )


if __name__ == "__main__":
    main()
