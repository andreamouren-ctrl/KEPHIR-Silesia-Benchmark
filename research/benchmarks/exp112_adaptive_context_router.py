#!/usr/bin/env python3
"""
EXP-112 — Adaptive Context Router Holdout

Research-only.

EXP-111 showed that a cheap file-level signal can nearly reproduce the
per-file context oracle on Silesia. EXP-112 freezes two candidate policies
before looking at a deterministic holdout corpus and measures whether they
generalize.

Measured configurations:
- baseline production path (512 KiB parent/context behavior);
- 4 MiB parent + 4 MiB inner context, adaptive grain;
- 8 MiB parent + 8 MiB inner context, adaptive grain.

Candidate routers:
A) spread-v1
   quarter entropy spread < 0.10 -> 8 MiB
   quarter entropy spread < 0.20 -> 4 MiB
   otherwise baseline

B) conservative-v1
   files < 2 MiB -> baseline
   sampled entropy >= 7.75 -> baseline
   quarter histogram TV max >= 0.18 -> baseline
   then use the same 0.10 / 0.20 spread thresholds.

The holdout contains deterministic unseen shapes with neutral names:
stable prose/code/structured binary/zero-rich, incompressible random,
entropy shifts, equal-entropy distribution shifts, mixed text families,
repeated pseudo-random blocks, and medium structured data.

Every measured archive is decoded by the ordinary decoder and SHA-256
verified. No production policy is changed by this experiment.
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
SILESIA_FILES = [
    "dickens", "mozilla", "mr", "nci", "ooffice", "osdb",
    "reymont", "samba", "sao", "webster", "x-ray", "xml",
]

BASELINE = "baseline"
CTX4 = "ctx4m"
CTX8 = "ctx8m"
CONFIGS = [
    {"label": BASELINE, "parent_kib": 0, "inner_kib": 0, "force": 0},
    {"label": CTX4, "parent_kib": 4096, "inner_kib": 4096, "force": 0},
    {"label": CTX8, "parent_kib": 8192, "inner_kib": 8192, "force": 0},
]

MiB = 1024 * 1024


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


def histogram(buf):
    counts = [0] * 256
    for b in buf:
        counts[b] += 1
    n = max(1, len(buf))
    return [c / n for c in counts]


def tv(a, b):
    return 0.5 * sum(abs(x - y) for x, y in zip(a, b))


def cheap_features(path):
    data = path.read_bytes()
    sample = stride_sample(data)
    n = max(1, len(sample))

    printable = sum(
        1 for b in sample
        if b in (9, 10, 13) or 32 <= b < 127
    ) / n
    zeros = sample.count(0) / n

    quarters = []
    if data:
        q = max(1, len(data) // 4)
        for i in range(4):
            start = i * q
            end = len(data) if i == 3 else min(len(data), (i + 1) * q)
            quarters.append(data[start:end])

    quarter_entropy = [
        entropy(stride_sample(part, 4096))
        for part in quarters
    ]
    spread = (
        max(quarter_entropy) - min(quarter_entropy)
        if quarter_entropy else 0.0
    )

    hists = [histogram(part) for part in quarters]
    pairwise = [
        tv(hists[i], hists[j])
        for i in range(len(hists))
        for j in range(i + 1, len(hists))
    ]
    tv_max = max(pairwise) if pairwise else 0.0

    return {
        "raw_bytes": len(data),
        "sample_entropy": entropy(sample),
        "sample_printable_fraction": printable,
        "sample_zero_fraction": zeros,
        "quarter_entropy_spread": spread,
        "quarter_tv_max": tv_max,
    }


def route_spread_v1(features):
    spread = features["quarter_entropy_spread"]
    if spread < 0.10:
        return CTX8
    if spread < 0.20:
        return CTX4
    return BASELINE


def route_conservative_v1(features):
    if features["raw_bytes"] < 2 * MiB:
        return BASELINE
    if features["sample_entropy"] >= 7.75:
        return BASELINE
    if features["quarter_tv_max"] >= 0.18:
        return BASELINE
    return route_spread_v1(features)


def write_repeat(path, pattern, size):
    pattern = bytes(pattern)
    if not pattern:
        raise ValueError("empty repeat pattern")
    reps = (size + len(pattern) - 1) // len(pattern)
    path.write_bytes((pattern * reps)[:size])


def make_holdout(root):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    one = 8 * MiB
    files = {}

    prose = (
        b"lossless compression benefits when repeated language structures "
        b"remain statistically stable across a long context window.\n"
    )
    code = (
        b"int transform(int x){return (x*31)+7;}\n"
        b"struct Row{int a;int b;int c;};\n"
    )
    record = bytes([
        0, 1, 0, 2, 16, 0, 32, 0,
        64, 0, 128, 0, 7, 7, 7, 7,
    ]) + b"ROW-DATA-" * 8
    zero_rich = (b"\x00" * 48) + bytes(range(16)) + (b"\xff" * 16)

    p = root / "h01.dat"
    write_repeat(p, prose, one)
    files["stable_prose"] = p

    p = root / "h02.dat"
    write_repeat(p, code, one)
    files["stable_code"] = p

    p = root / "h03.dat"
    write_repeat(p, record, one)
    files["stable_structured_binary"] = p

    p = root / "h04.dat"
    write_repeat(p, zero_rich, one)
    files["stable_zero_rich"] = p

    rng = random.Random(11205)
    p = root / "h05.dat"
    p.write_bytes(rng.randbytes(one))
    files["uniform_random"] = p

    # Strong entropy shift: two highly compressible quarters followed by two
    # incompressible quarters. A long global context should not be trusted.
    rng = random.Random(11206)
    p = root / "h06.dat"
    p.write_bytes(
        (b"ABCD" * (MiB // 2))
        + (b"01234567" * (MiB // 4))
        + rng.randbytes(2 * MiB)
        + rng.randbytes(2 * MiB)
    )
    files["entropy_shift"] = p

    # Similar entropy in every quarter but a very different symbol alphabet.
    # This is the counterexample that entropy spread alone cannot see.
    p = root / "h07.dat"
    quarters = []
    for base in (0, 64, 128, 192):
        alphabet = bytes(range(base, base + 64))
        quarters.append((alphabet * ((2 * MiB + 63) // 64))[:2 * MiB])
    p.write_bytes(b"".join(quarters))
    files["equal_entropy_distribution_shift"] = p

    # Different textual families with fairly high printable content.
    p = root / "h08.dat"
    q = 2 * MiB
    text_parts = [
        (prose * ((q + len(prose) - 1) // len(prose)))[:q],
        (code * ((q + len(code) - 1) // len(code)))[:q],
        (b"name: value\nmode: fast\npath: /data/item\n" * 65536)[:q],
        (b"<row><item>value</item><flag>true</flag></row>\n" * 65536)[:q],
    ]
    p.write_bytes(b"".join(text_parts))
    files["mixed_text_families"] = p

    # High byte entropy but strong long-range repetition.
    rng = random.Random(11209)
    block = rng.randbytes(512 * 1024)
    p = root / "h09.dat"
    p.write_bytes(block * 16)
    files["repeated_pseudorandom_block"] = p

    # Medium-size structured stream; verifies the minimum-size guard does not
    # hide a useful 4 MiB context opportunity.
    p = root / "h10.dat"
    write_repeat(p, record + prose[:32], 3 * MiB)
    files["medium_structured"] = p

    return files


def measure_file(cli, src, work, dataset, name, cfg):
    safe = dataset.replace("/", "_")
    arc = work / f"{safe}_{name}_{cfg['label']}.kpf"
    out = work / f"out_{safe}_{name}_{cfg['label']}"

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
            f"SHA mismatch dataset={dataset} file={name} cfg={cfg['label']}"
        )

    row = {
        "archive_bytes": arc.stat().st_size,
        "comp_seconds": float(cm["SECONDS"]),
        "dec_seconds": float(dm["SECONDS"]),
        "sha_pass": True,
    }

    shutil.rmtree(out)
    arc.unlink()
    return row


def evaluate_dataset(cli, work, dataset, files):
    rows = []
    for logical_name, src in files.items():
        feat = cheap_features(src)
        measured = {}
        for cfg in CONFIGS:
            measured[cfg["label"]] = measure_file(
                cli, src, work, dataset, logical_name, cfg
            )

        best_label = min(
            measured,
            key=lambda label: (
                measured[label]["archive_bytes"],
                [BASELINE, CTX4, CTX8].index(label),
            ),
        )

        row = {
            "file": logical_name,
            "path": str(src),
            "features": feat,
            "measured": measured,
            "oracle": best_label,
            "spread_v1": route_spread_v1(feat),
            "conservative_v1": route_conservative_v1(feat),
        }
        rows.append(row)

        print(
            "EXP112_FILE",
            dataset,
            logical_name,
            "H", feat["sample_entropy"],
            "SPREAD", feat["quarter_entropy_spread"],
            "TV", feat["quarter_tv_max"],
            "ORACLE", best_label,
            "SPREAD_V1", row["spread_v1"],
            "CONS_V1", row["conservative_v1"],
            flush=True,
        )

    raw_total = sum(r["features"]["raw_bytes"] for r in rows)
    baseline_total = sum(
        r["measured"][BASELINE]["archive_bytes"] for r in rows
    )
    oracle_total = sum(
        r["measured"][r["oracle"]]["archive_bytes"] for r in rows
    )

    result = {
        "dataset": dataset,
        "raw_bytes": raw_total,
        "baseline_bytes": baseline_total,
        "oracle_bytes": oracle_total,
        "oracle_gain": baseline_total - oracle_total,
        "files": rows,
    }

    for policy in ("spread_v1", "conservative_v1"):
        chosen_total = sum(
            r["measured"][r[policy]]["archive_bytes"]
            for r in rows
        )
        harmful = []
        correct = 0
        for r in rows:
            chosen = r[policy]
            if chosen == r["oracle"]:
                correct += 1
            delta = (
                r["measured"][chosen]["archive_bytes"]
                - r["measured"][BASELINE]["archive_bytes"]
            )
            if delta > 0:
                harmful.append({
                    "file": r["file"],
                    "chosen": chosen,
                    "delta_vs_baseline": delta,
                })

        result[policy] = {
            "archive_bytes": chosen_total,
            "ratio": chosen_total / raw_total,
            "gain_vs_baseline": baseline_total - chosen_total,
            "regret_vs_oracle": chosen_total - oracle_total,
            "oracle_exact": correct,
            "files": len(rows),
            "harmful_selections": harmful,
        }

    print(
        "EXP112_DATASET",
        dataset,
        "BASE", baseline_total,
        "ORACLE", oracle_total,
        "SPREAD", result["spread_v1"]["archive_bytes"],
        "CONS", result["conservative_v1"]["archive_bytes"],
        "SPREAD_HARM", len(result["spread_v1"]["harmful_selections"]),
        "CONS_HARM", len(result["conservative_v1"]["harmful_selections"]),
        flush=True,
    )

    return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: exp112_adaptive_context_router.py NATIVE_K75_CLI"
        )

    cli = Path(sys.argv[1]).resolve()
    corpus = ROOT / "corpora" / "silesia"
    work = ROOT / "exp112_adaptive_context_router"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia = {
        name: corpus / name
        for name in SILESIA_FILES
    }
    holdout = make_holdout(work / "holdout")

    silesia_result = evaluate_dataset(
        cli, work, "silesia-training", silesia
    )
    holdout_result = evaluate_dataset(
        cli, work, "deterministic-holdout", holdout
    )

    result = {
        "experiment": "EXP-112",
        "purpose": "adaptive-context-router-holdout",
        "policies_frozen_before_holdout": {
            "spread_v1": {
                "spread_lt_0_10": CTX8,
                "spread_lt_0_20": CTX4,
                "else": BASELINE,
            },
            "conservative_v1": {
                "min_bytes": 2 * MiB,
                "max_entropy_for_long_context": 7.75,
                "max_quarter_tv": 0.18,
                "then": "spread_v1",
            },
        },
        "datasets": [
            silesia_result,
            holdout_result,
        ],
    }

    Path("exp112_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )

    assert silesia_result["raw_bytes"] == 211938580
    assert all(
        m["sha_pass"]
        for ds in result["datasets"]
        for row in ds["files"]
        for m in row["measured"].values()
    )

    print(
        "EXP112_COMPLETE",
        "SILESIA_CONS_GAIN",
        silesia_result["conservative_v1"]["gain_vs_baseline"],
        "HOLDOUT_CONS_GAIN",
        holdout_result["conservative_v1"]["gain_vs_baseline"],
        "HOLDOUT_CONS_HARM",
        len(holdout_result["conservative_v1"]["harmful_selections"]),
        flush=True,
    )


if __name__ == "__main__":
    main()
