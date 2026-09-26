#!/usr/bin/env python3
"""
KASH-02: cheap audio recovery-horizon predictor discovery.

R&D flow:
1. Build an expensive KASH oracle cache with 1 s / 2 s candidate encodes.
2. Derive local split-benefit labels from actual KHEPRI payload sizes.
3. Compute cheap PCM-only features around each 1-second boundary.
4. Select ONE feature + ONE threshold by blocked cross-validation.
5. Freeze that rule and choose 1 s / 2 s segments without consulting encoded sizes.
6. Encode only the selected segments once and verify final AUM losslessly.

The oracle is research-only. The candidate production path performs no duplicate
candidate encodes.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from aurora_media_container import (
    AuroraMuxer,
    AuroraDemuxer,
    Track,
    TRACK_AUDIO,
    CODEC_AURORA_AUDIO,
    PKT_RECOVERY,
)
from aurora_media_codec_bridge import encode_audio_packet, decode_audio_packet

RATE = 48_000
CH = 2
BITS = 16
TS = 1_000_000
FB = CH * (BITS // 8)
META = 64
OUT = Path("results/audio/kash02")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def us(samples: int) -> int:
    return samples * TS // RATE


def encode_range(pcm: bytes, start: int, count: int, exe: Path):
    t0 = time.perf_counter()
    payload = encode_audio_packet(
        pcm[start * FB : (start + count) * FB], exe, CH, RATE
    )
    return payload, time.perf_counter() - t0


def build_oracle_cache(pcm: bytes, exe: Path):
    total = len(pcm) // FB
    positions = sorted(set(list(range(0, total, RATE)) + [total]))
    cache = {}
    encode_seconds = 0.0
    encode_count = 0

    for start in positions[:-1]:
        for seconds in (1, 2):
            end = min(total, start + seconds * RATE)
            if end <= start:
                continue
            payload, dt = encode_range(pcm, start, end - start, exe)
            cache[(start, end)] = payload
            encode_seconds += dt
            encode_count += 1

    return cache, positions, encode_seconds, encode_count


def oracle_dp(cache, positions):
    total = positions[-1]
    dp = {total: (0, [])}

    for start in reversed(positions[:-1]):
        best = None
        for seconds in (1, 2):
            end = min(total, start + seconds * RATE)
            if (start, end) not in cache or end not in dp:
                continue
            payload = cache[(start, end)]
            cand = (
                len(payload) + META + dp[end][0],
                [(start, end - start, payload)] + dp[end][1],
            )
            if best is None or cand[0] < best[0]:
                best = cand
        if best is None:
            raise RuntimeError("oracle DP found no path")
        dp[start] = best

    return dp[0]


def segment_stats(samples: np.ndarray):
    # samples: shape [frames, 2], int32
    if len(samples) < 2:
        return {
            "level": 0.0,
            "diff": 0.0,
            "mid_diff": 0.0,
            "side": 0.0,
            "side_diff": 0.0,
            "crest": 0.0,
            "zcr": 0.0,
        }

    left = samples[:, 0].astype(np.int64, copy=False)
    right = samples[:, 1].astype(np.int64, copy=False)
    mid = left + right
    side = left - right

    abs_samples = np.abs(samples.astype(np.int64, copy=False))
    diff_lr = np.diff(samples.astype(np.int64, copy=False), axis=0)
    diff_mid = np.diff(mid)
    diff_side = np.diff(side)

    level = float(np.mean(abs_samples))
    diff = float(np.mean(np.abs(diff_lr)))
    mid_diff = float(np.mean(np.abs(diff_mid)))
    side_mean = float(np.mean(np.abs(side)))
    side_diff = float(np.mean(np.abs(diff_side)))
    peak = float(np.max(abs_samples))
    crest = peak / (level + 1.0)

    # Cheap time-domain activity proxy.
    signs = mid >= 0
    zcr = float(np.mean(signs[1:] != signs[:-1]))

    return {
        "level": level,
        "diff": diff,
        "mid_diff": mid_diff,
        "side": side_mean,
        "side_diff": side_diff,
        "crest": crest,
        "zcr": zcr,
    }


def safe_log_ratio(a: float, b: float) -> float:
    return abs(math.log2((a + 1.0) / (b + 1.0)))


def boundary_features(frames: np.ndarray, start: int):
    mid = start + RATE
    end = start + 2 * RATE
    a = frames[start:mid]
    b = frames[mid:end]
    if len(a) != RATE or len(b) != RATE:
        raise ValueError("KASH-02 feature window requires two complete seconds")

    sa = segment_stats(a)
    sb = segment_stats(b)

    jump = float(np.mean(np.abs(
        b[0].astype(np.int64) - a[-1].astype(np.int64)
    )))

    mean_diff = 0.5 * (sa["diff"] + sb["diff"])
    mean_mid_diff = 0.5 * (sa["mid_diff"] + sb["mid_diff"])
    mean_side_diff = 0.5 * (sa["side_diff"] + sb["side_diff"])

    return {
        "level_change": safe_log_ratio(sa["level"], sb["level"]),
        "diff_change": safe_log_ratio(sa["diff"], sb["diff"]),
        "mid_diff_change": safe_log_ratio(sa["mid_diff"], sb["mid_diff"]),
        "side_change": safe_log_ratio(sa["side"], sb["side"]),
        "side_diff_change": safe_log_ratio(sa["side_diff"], sb["side_diff"]),
        "crest_change": abs(sa["crest"] - sb["crest"]),
        "zcr_change": abs(sa["zcr"] - sb["zcr"]),
        "boundary_jump_norm": jump / (mean_diff + 1.0),
        "boundary_jump_mid_norm": jump / (mean_mid_diff + 1.0),
        "activity": mean_diff,
        "mid_activity": mean_mid_diff,
        "side_activity": mean_side_diff,
    }


def make_label_rows(pcm: bytes, cache, total: int):
    raw = np.frombuffer(pcm, dtype="<i2")
    if raw.size % CH:
        raise RuntimeError("PCM sample count is not channel aligned")
    frames = raw.reshape(-1, CH).astype(np.int32)

    rows = []
    for start in range(0, total - 2 * RATE + 1, RATE):
        one_a = cache[(start, start + RATE)]
        one_b = cache[(start + RATE, start + 2 * RATE)]
        two = cache[(start, start + 2 * RATE)]

        split_bytes = len(one_a) + META + len(one_b) + META
        joined_bytes = len(two) + META
        split_delta = split_bytes - joined_bytes

        rows.append({
            "start_second": start // RATE,
            "split_beneficial": split_delta < 0,
            "split_delta_bytes": int(split_delta),
            "weight": float(abs(split_delta) + 1),
            "features": boundary_features(frames, start),
        })

    return rows


def thresholds(values):
    vals = sorted(set(float(v) for v in values))
    if not vals:
        return [0.0]
    if len(vals) == 1:
        return [vals[0]]
    out = [vals[0] - max(1e-12, abs(vals[0]) * 1e-9 + 1e-12)]
    out.extend((a + b) * 0.5 for a, b in zip(vals, vals[1:]))
    out.append(vals[-1] + max(1e-12, abs(vals[-1]) * 1e-9 + 1e-12))
    return out


def predict_value(value: float, op: str, threshold: float) -> bool:
    if op == "ge":
        return value >= threshold
    if op == "le":
        return value <= threshold
    raise ValueError(op)


def fit_rule(rows, feature: str, op: str, train_indices):
    vals = [rows[i]["features"][feature] for i in train_indices]
    best = None

    for threshold in thresholds(vals):
        wrong_weight = 0.0
        total_weight = 0.0
        false_splits = 0
        for i in train_indices:
            row = rows[i]
            pred = predict_value(row["features"][feature], op, threshold)
            truth = bool(row["split_beneficial"])
            w = float(row["weight"])
            total_weight += w
            if pred != truth:
                wrong_weight += w
            if pred and not truth:
                false_splits += 1

        score = wrong_weight / total_weight if total_weight else 0.0
        key = (score, false_splits, threshold)
        if best is None or key < best[0]:
            best = (key, threshold)

    return best[1]


def eval_rule(rows, feature: str, op: str, threshold: float, indices):
    correct = 0
    total = 0
    correct_weight = 0.0
    total_weight = 0.0
    tp = fp = tn = fn = 0

    for i in indices:
        row = rows[i]
        pred = predict_value(row["features"][feature], op, threshold)
        truth = bool(row["split_beneficial"])
        w = float(row["weight"])

        total += 1
        total_weight += w
        if pred == truth:
            correct += 1
            correct_weight += w

        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif (not pred) and (not truth):
            tn += 1
        else:
            fn += 1

    return {
        "accuracy": correct / total if total else 0.0,
        "weighted_accuracy": correct_weight / total_weight if total_weight else 0.0,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def blocked_folds(count: int, k: int = 4):
    indices = list(range(count))
    folds = []
    for fold in range(k):
        lo = count * fold // k
        hi = count * (fold + 1) // k
        folds.append(indices[lo:hi])
    return folds


def select_rule(rows):
    feature_names = sorted(rows[0]["features"].keys())
    folds = blocked_folds(len(rows), 4)
    candidates = []

    for feature in feature_names:
        for op in ("ge", "le"):
            fold_metrics = []
            for held in folds:
                held_set = set(held)
                train = [i for i in range(len(rows)) if i not in held_set]
                if not train or not held:
                    continue
                threshold = fit_rule(rows, feature, op, train)
                metrics = eval_rule(rows, feature, op, threshold, held)
                fold_metrics.append(metrics)

            cv_weighted = float(np.mean(
                [m["weighted_accuracy"] for m in fold_metrics]
            ))
            cv_accuracy = float(np.mean(
                [m["accuracy"] for m in fold_metrics]
            ))
            final_threshold = fit_rule(
                rows, feature, op, list(range(len(rows)))
            )
            full_metrics = eval_rule(
                rows, feature, op, final_threshold, list(range(len(rows)))
            )
            candidates.append({
                "feature": feature,
                "op": op,
                "threshold": final_threshold,
                "cv_weighted_accuracy": cv_weighted,
                "cv_accuracy": cv_accuracy,
                "full_metrics": full_metrics,
            })

    candidates.sort(
        key=lambda c: (
            -c["cv_weighted_accuracy"],
            -c["cv_accuracy"],
            -c["full_metrics"]["weighted_accuracy"],
            c["feature"],
            c["op"],
        )
    )
    return candidates[0], candidates[:10]


def choose_segments_from_rule(pcm: bytes, total: int, rule):
    raw = np.frombuffer(pcm, dtype="<i2")
    frames = raw.reshape(-1, CH).astype(np.int32)

    feature = rule["feature"]
    op = rule["op"]
    threshold = float(rule["threshold"])

    entries = []
    start = 0
    decision_seconds = 0.0
    one_count = 0
    two_count = 0

    while start < total:
        remaining = total - start
        if remaining <= RATE:
            count = remaining
            one_count += 1
        elif remaining < 2 * RATE:
            count = remaining
            one_count += 1
        else:
            t0 = time.perf_counter()
            feats = boundary_features(frames, start)
            split = predict_value(feats[feature], op, threshold)
            decision_seconds += time.perf_counter() - t0
            count = RATE if split else 2 * RATE
            if split:
                one_count += 1
            else:
                two_count += 1

        entries.append((start, count))
        start += count

    return entries, decision_seconds, one_count, two_count


def encode_segments(pcm: bytes, segments, exe: Path):
    encoded = []
    total_seconds = 0.0
    for start, count in segments:
        payload, dt = encode_range(pcm, start, count, exe)
        encoded.append((start, count, payload))
        total_seconds += dt
    return encoded, total_seconds


def fixed_segments(total: int):
    step = 2 * RATE
    return [
        (start, min(step, total - start))
        for start in range(0, total, step)
    ]


def write_verify(name: str, entries, pcm: bytes, exe: Path):
    path = OUT / f"{name}.aum"
    with AuroraMuxer(
        path,
        [Track(
            1,
            TRACK_AUDIO,
            CODEC_AURORA_AUDIO,
            0,
            RATE,
            CH,
            BITS,
            2 * RATE,
        )],
    ) as mux:
        for start, count, payload in entries:
            mux.write_packet(
                1, us(start), us(count), payload, PKT_RECOVERY
            )

    decoded = bytearray()
    decode_seconds = 0.0
    with AuroraDemuxer(path) as demux:
        for _, payload in demux.packets(1):
            t0 = time.perf_counter()
            decoded.extend(decode_audio_packet(payload, exe))
            decode_seconds += time.perf_counter() - t0

    ok = sha(bytes(decoded)) == sha(pcm)
    if not ok:
        raise RuntimeError(f"{name}: SHA mismatch")

    horizons = [round(count / RATE, 6) for _, count, _ in entries]
    return {
        "bytes": path.stat().st_size,
        "packets": len(entries),
        "horizons": horizons,
        "decode_seconds": decode_seconds,
        "sha_ok": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--kephir", type=Path, required=True)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pcm = args.audio.read_bytes()
    total = len(pcm) // FB

    oracle_cache, positions, oracle_search_seconds, oracle_encode_count = (
        build_oracle_cache(pcm, args.kephir)
    )
    oracle_objective, oracle_entries = oracle_dp(oracle_cache, positions)

    feature_t0 = time.perf_counter()
    label_rows = make_label_rows(pcm, oracle_cache, total)
    best_rule, top_rules = select_rule(label_rows)
    feature_model_seconds = time.perf_counter() - feature_t0

    predicted_segments, decision_seconds, one_count, two_count = (
        choose_segments_from_rule(pcm, total, best_rule)
    )

    fixed_encoded, fixed_encode_seconds = encode_segments(
        pcm, fixed_segments(total), args.kephir
    )
    predicted_encoded, predicted_encode_seconds = encode_segments(
        pcm, predicted_segments, args.kephir
    )

    fixed_result = write_verify(
        "fixed_2s", fixed_encoded, pcm, args.kephir
    )
    fixed_result["encode_seconds"] = fixed_encode_seconds

    oracle_result = write_verify(
        "oracle_1_2s", oracle_entries, pcm, args.kephir
    )
    oracle_result["search_encode_seconds"] = oracle_search_seconds
    oracle_result["oracle_encode_count"] = oracle_encode_count
    oracle_result["objective_bytes_excluding_fixed_container"] = oracle_objective

    predictor_result = write_verify(
        "predictor_1_2s", predicted_encoded, pcm, args.kephir
    )
    predictor_result.update({
        "encode_seconds": predicted_encode_seconds,
        "decision_seconds": decision_seconds,
        "feature_model_seconds_rnd_only": feature_model_seconds,
        "count_1s": one_count,
        "count_2s": two_count,
    })

    fixed_bytes = fixed_result["bytes"]
    oracle_bytes = oracle_result["bytes"]
    predictor_bytes = predictor_result["bytes"]

    available_gain = fixed_bytes - oracle_bytes
    recovered_gain = fixed_bytes - predictor_bytes
    recovery_percent = (
        100.0 * recovered_gain / available_gain
        if available_gain > 0 else 0.0
    )

    local_beneficial = sum(
        1 for row in label_rows if row["split_beneficial"]
    )

    result = {
        "experiment": "KASH-02 cheap reset-benefit predictor",
        "audio_raw_bytes": len(pcm),
        "seconds": total / RATE,
        "fixed_2s": fixed_result,
        "oracle": oracle_result,
        "predictor": predictor_result,
        "candidate_rule": best_rule,
        "top_rules": top_rules,
        "local_training_rows": len(label_rows),
        "local_split_beneficial_rows": local_beneficial,
        "oracle_delta_bytes_vs_fixed": oracle_bytes - fixed_bytes,
        "predictor_delta_bytes_vs_fixed": predictor_bytes - fixed_bytes,
        "oracle_gain_recovered_percent": recovery_percent,
        "decision_cost_ratio_vs_oracle_search": (
            decision_seconds / oracle_search_seconds
            if oracle_search_seconds > 0 else 0.0
        ),
        "production_candidate_duplicate_encodes": 0,
        "note": (
            "Rule discovery is trained on this corpus and is not a production "
            "promotion. A fixed rule must be validated on unseen audio corpora."
        ),
    }

    (OUT / "KASH02_RESULTS.json").write_text(
        json.dumps(result, indent=2)
    )

    # Compact human-readable summary for CI logs.
    print("KASH02_PASS")
    print(
        "RULE",
        best_rule["feature"],
        best_rule["op"],
        f"{best_rule['threshold']:.12g}",
        "cv_weighted_accuracy",
        f"{best_rule['cv_weighted_accuracy']:.6f}",
        "cv_accuracy",
        f"{best_rule['cv_accuracy']:.6f}",
    )
    print(
        "BYTES",
        "fixed", fixed_bytes,
        "oracle", oracle_bytes,
        "predictor", predictor_bytes,
        "recovered_percent", f"{recovery_percent:.3f}",
    )
    print(
        "COST",
        "oracle_search_s", f"{oracle_search_seconds:.6f}",
        "predictor_decision_s", f"{decision_seconds:.6f}",
        "predictor_encode_s", f"{predicted_encode_seconds:.6f}",
        "duplicate_encodes", 0,
    )


if __name__ == "__main__":
    main()
