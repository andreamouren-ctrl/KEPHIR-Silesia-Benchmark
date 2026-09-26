#!/usr/bin/env python3
"""
KASH-03: unseen multi-corpus validation of the frozen KASH-02 recovery rule.

The predictor is NOT retrained here. The rule learned on the Sintel checkpoint is
frozen and evaluated on independent lossless film-audio sources.

Research oracle:
- may encode both 1 s and 2 s candidates;
- exists only to measure the available adaptive-horizon gain.

Candidate production predictor:
- uses PCM features only;
- performs zero duplicate candidate encodes;
- every chosen segment is encoded exactly once.
"""
import argparse
import json
from pathlib import Path

import kash02_reset_predictor as k2

RATE = 48_000
CH = 2
BITS = 16
FB = CH * (BITS // 8)
OUT = Path("results/audio/kash03")

FROZEN_RULE = {
    "feature": "diff_change",
    "op": "ge",
    "threshold": 2.0409084219,
    "source_checkpoint": "KASH-02 canonical / Sintel",
}


def parse_source(value: str):
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source must be name=path")
    name, raw = value.split("=", 1)
    if not name or not raw:
        raise argparse.ArgumentTypeError("--source must be name=path")
    return name, Path(raw)


def run_source(name: str, raw_path: Path, exe: Path):
    pcm = raw_path.read_bytes()
    if len(pcm) % FB:
        raise RuntimeError(f"{name}: PCM is not frame aligned")
    total = len(pcm) // FB
    if total < 2 * RATE:
        raise RuntimeError(f"{name}: source is shorter than 2 seconds")

    cache, positions, oracle_search_seconds, oracle_encode_count = (
        k2.build_oracle_cache(pcm, exe)
    )
    oracle_objective, oracle_entries = k2.oracle_dp(cache, positions)

    predicted_segments, decision_seconds, one_count, two_count = (
        k2.choose_segments_from_rule(pcm, total, FROZEN_RULE)
    )

    fixed_encoded, fixed_encode_seconds = k2.encode_segments(
        pcm, k2.fixed_segments(total), exe
    )
    predicted_encoded, predicted_encode_seconds = k2.encode_segments(
        pcm, predicted_segments, exe
    )

    source_out = OUT / name
    source_out.mkdir(parents=True, exist_ok=True)
    old_out = k2.OUT
    k2.OUT = source_out
    try:
        fixed = k2.write_verify("fixed_2s", fixed_encoded, pcm, exe)
        oracle = k2.write_verify("oracle_1_2s", oracle_entries, pcm, exe)
        predictor = k2.write_verify("predictor_1_2s", predicted_encoded, pcm, exe)
    finally:
        k2.OUT = old_out

    fixed["encode_seconds"] = fixed_encode_seconds
    oracle["search_encode_seconds"] = oracle_search_seconds
    oracle["oracle_encode_count"] = oracle_encode_count
    oracle["objective_bytes_excluding_fixed_container"] = oracle_objective
    predictor.update({
        "encode_seconds": predicted_encode_seconds,
        "decision_seconds": decision_seconds,
        "count_1s": one_count,
        "count_2s": two_count,
    })

    fixed_bytes = fixed["bytes"]
    oracle_bytes = oracle["bytes"]
    predictor_bytes = predictor["bytes"]
    available = fixed_bytes - oracle_bytes
    recovered = fixed_bytes - predictor_bytes

    return {
        "name": name,
        "raw_bytes": len(pcm),
        "seconds": total / RATE,
        "fixed_2s": fixed,
        "oracle": oracle,
        "predictor": predictor,
        "oracle_gain_bytes": available,
        "predictor_gain_bytes": recovered,
        "predictor_delta_percent_vs_fixed": (
            100.0 * (predictor_bytes - fixed_bytes) / fixed_bytes
        ),
        "oracle_gain_recovered_percent": (
            100.0 * recovered / available if available > 0 else 0.0
        ),
        "production_candidate_duplicate_encodes": 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kephir", type=Path, required=True)
    ap.add_argument(
        "--source",
        action="append",
        type=parse_source,
        required=True,
        help="name=raw_pcm_path; repeat for each unseen source",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rows = [run_source(name, path, args.kephir) for name, path in args.source]

    fixed_total = sum(r["fixed_2s"]["bytes"] for r in rows)
    oracle_total = sum(r["oracle"]["bytes"] for r in rows)
    predictor_total = sum(r["predictor"]["bytes"] for r in rows)
    oracle_gain = fixed_total - oracle_total
    predictor_gain = fixed_total - predictor_total

    max_regression_pct = max(
        (r["predictor_delta_percent_vs_fixed"] for r in rows),
        default=0.0,
    )
    positive_sources = sum(1 for r in rows if r["predictor_gain_bytes"] > 0)

    result = {
        "experiment": "KASH-03 frozen-rule unseen multi-corpus validation",
        "frozen_rule": FROZEN_RULE,
        "sources": rows,
        "aggregate": {
            "fixed_2s_bytes": fixed_total,
            "oracle_bytes": oracle_total,
            "predictor_bytes": predictor_total,
            "oracle_gain_bytes": oracle_gain,
            "predictor_gain_bytes": predictor_gain,
            "predictor_delta_percent_vs_fixed": (
                100.0 * (predictor_total - fixed_total) / fixed_total
            ),
            "oracle_gain_recovered_percent": (
                100.0 * predictor_gain / oracle_gain if oracle_gain > 0 else 0.0
            ),
            "positive_sources": positive_sources,
            "source_count": len(rows),
            "worst_source_regression_percent": max_regression_pct,
        },
        "production_candidate_duplicate_encodes": 0,
    }

    # Conservative research gate. A later production gate will require a much
    # larger corpus, but KASH-03 should at least generalize across every source
    # in this unseen film-audio set without a per-source regression.
    result["promotion_candidate"] = (
        predictor_total < fixed_total
        and positive_sources == len(rows)
        and max_regression_pct <= 0.0
    )

    out = OUT / "KASH03_RESULTS.json"
    out.write_text(json.dumps(result, indent=2))

    print("KASH03_PASS")
    print(
        "AGGREGATE",
        "fixed", fixed_total,
        "oracle", oracle_total,
        "predictor", predictor_total,
        "oracle_gain", oracle_gain,
        "predictor_gain", predictor_gain,
        "recovered_percent",
        f"{result['aggregate']['oracle_gain_recovered_percent']:.3f}",
        "promotion_candidate", result["promotion_candidate"],
    )
    for r in rows:
        print(
            "SOURCE",
            r["name"],
            "fixed", r["fixed_2s"]["bytes"],
            "oracle", r["oracle"]["bytes"],
            "predictor", r["predictor"]["bytes"],
            "gain", r["predictor_gain_bytes"],
            "delta_pct", f"{r['predictor_delta_percent_vs_fixed']:.6f}",
            "recovered_pct", f"{r['oracle_gain_recovered_percent']:.3f}",
            "decision_s", f"{r['predictor']['decision_seconds']:.6f}",
        )


if __name__ == "__main__":
    main()
