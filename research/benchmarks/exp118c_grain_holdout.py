#!/usr/bin/env python3
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

MiB = 1024 * 1024
KiB = 1024
FULL = {
    "adaptive": ["adaptive"],
    "grain4": ["4096", "4096", "1"],
    "grain8": ["8192", "8192", "1"],
}


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
        for block in iter(lambda: f.read(MiB), b""):
            h.update(block)
    return h.hexdigest()


def repeat(pattern, size):
    return (pattern * ((size + len(pattern) - 1) // len(pattern)))[:size]


def pseudo_random(size, seed):
    return random.Random(seed).randbytes(size)


def entropy(data):
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def stride_sample(data, n):
    if len(data) <= n:
        return data
    step = max(1, len(data) // n)
    return data[::step][:n]


def cheap_features(data):
    if not data:
        return {"bytes": 0, "entropy": 0.0, "quarter_entropy_spread": 0.0}
    n = len(data)
    q = max(1, n // 4)
    hs = []
    for i in range(4):
        lo = i * q
        hi = n if i == 3 else min(n, (i + 1) * q)
        hs.append(entropy(stride_sample(data[lo:hi], 4096)))
    return {
        "bytes": n,
        "entropy": entropy(stride_sample(data, 16384)),
        "quarter_entropy_spread": max(hs) - min(hs),
        "quarter_entropies": hs,
    }


def feature_choice(features):
    # Frozen before EXP-118C. Derived on EXP-118A measured data only.
    if features["bytes"] >= 2 * MiB and (
        features["entropy"] < 6.4
        or (
            features["entropy"] < 7.0
            and features["quarter_entropy_spread"] < 0.20
        )
    ):
        return "grain8"
    return "adaptive"


def stratified_2m(data):
    budget = 2 * MiB
    if len(data) <= budget:
        return data
    parts = 4
    chunk = budget // parts
    maxoff = len(data) - chunk
    offsets = [(maxoff * i) // (parts - 1) for i in range(parts)]
    out = bytearray()
    for off in offsets:
        out.extend(data[off:off + chunk])
    return bytes(out[:budget])


def make_raster(width, rows, seed, noise=3):
    rng = random.Random(seed)
    row = bytearray(rng.randrange(256) for _ in range(width))
    out = bytearray(row)
    for r in range(1, rows):
        nxt = bytearray(width)
        drift = (r * 3) & 255
        for x, v in enumerate(row):
            nxt[x] = (v + drift + rng.randrange(-noise, noise + 1)) & 255
        out.extend(nxt)
        row = nxt
    return bytes(out)


def make_equal_entropy_shift(size, seed):
    rng = random.Random(seed)
    quarter = size // 4
    pools = [
        list(range(0, 64)),
        list(range(64, 128)),
        list(range(128, 192)),
        list(range(192, 256)),
    ]
    out = bytearray()
    for pool in pools:
        out.extend(bytes(rng.choice(pool) for _ in range(quarter)))
    if len(out) < size:
        out.extend(bytes(rng.choice(pools[-1]) for _ in range(size - len(out))))
    return bytes(out)


def make_structured_records(size):
    out = bytearray()
    i = 0
    while len(out) < size:
        rec = (
            i.to_bytes(4, "little")
            + ((i * 2654435761) & 0xffffffff).to_bytes(4, "little")
            + bytes([0, 0, i & 255, (i >> 8) & 255])
            + b"REC|KEPHIR|"
        )
        out.extend(rec)
        i += 1
    return bytes(out[:size])


def build_cases(root):
    root.mkdir(parents=True, exist_ok=True)
    cases = {}

    cases["stable_prose_6m"] = repeat(
        b"ordinary prose words and spaces form a natural sentence; long range context remains stable.\n",
        6 * MiB,
    )
    cases["stable_code_6m"] = repeat(
        b"int transform(int x){ return (x * 33) ^ (x >> 3); } // deterministic code\n",
        6 * MiB,
    )
    cases["structured_records_6m"] = make_structured_records(6 * MiB)
    cases["uniform_random_6m"] = pseudo_random(6 * MiB, 11801)

    # Abrupt entropy/content changes: dangerous for long parent assumptions.
    cases["entropy_shift_8m"] = (
        repeat(b"ABCD", 2 * MiB)
        + pseudo_random(2 * MiB, 11802)
        + repeat(b"0123456789abcdef", 2 * MiB)
        + pseudo_random(2 * MiB, 11803)
    )
    cases["equal_entropy_distribution_shift_8m"] = make_equal_entropy_shift(8 * MiB, 11804)

    block = pseudo_random(256 * KiB, 11805)
    cases["repeated_pseudorandom_block_8m"] = repeat(block, 8 * MiB)

    cases["mixed_text_families_6m"] = (
        repeat(b"natural language prose with spaces and common words.\n", 2 * MiB)
        + repeat(b"<node id=\"42\"><value>structured markup</value></node>\n", 2 * MiB)
        + repeat(b"mov rax, rbx ; xor rcx, rcx ; add rax, 17\n", 2 * MiB)
    )

    # High entropy stream with sparse deterministic headers.
    rng = random.Random(11806)
    noisy = bytearray()
    while len(noisy) < 6 * MiB:
        noisy.extend(b"CHNK" + len(noisy).to_bytes(4, "little"))
        noisy.extend(rng.randbytes(64 * KiB - 8))
    cases["sparse_headers_random_6m"] = bytes(noisy[:6 * MiB])

    # Threshold cases around the frozen feature gate.
    cases["stable_1536k"] = repeat(b"threshold stable payload 1536k\n", 1536 * KiB)
    cases["stable_2m"] = repeat(b"threshold stable payload two megabytes\n", 2 * MiB)
    cases["stable_4m"] = repeat(b"threshold stable payload four megabytes\n", 4 * MiB)

    # Raster-like row-correlated streams at widths not represented by the current fixed 1024 mode.
    cases["raster_w256_4m"] = make_raster(256, (4 * MiB) // 256, 11807, 2)
    cases["raster_w512_4m"] = make_raster(512, (4 * MiB) // 512, 11808, 2)
    cases["raster_w2048_4m"] = make_raster(2048, (4 * MiB) // 2048, 11809, 2)
    cases["raster_w4096_4m"] = make_raster(4096, (4 * MiB) // 4096, 11810, 2)

    for name, data in cases.items():
        (root / f"{name}.bin").write_bytes(data)
    return sorted(root.glob("*.bin"))


def compress(cli, src, archive, extra):
    r = run([str(cli), "c", str(src), str(archive), "4", *extra])
    return {"bytes": int(r["OUTPUT_BYTES"]), "seconds": float(r["SECONDS"])}


def measure_full(cli, src, work, idx):
    source_sha = sha256(src)
    rows = {}
    for name, extra in FULL.items():
        archive = work / f"full_{idx:02d}_{name}.kpf"
        outdir = work / f"full_{idx:02d}_{name}_out"
        shutil.rmtree(outdir, ignore_errors=True)
        enc = compress(cli, src, archive, extra)
        dec = run([str(cli), "d", str(archive), str(outdir), "4"])
        restored = outdir / src.name
        ok = restored.is_file() and sha256(restored) == source_sha
        if not ok:
            raise RuntimeError(f"roundtrip failure: {src.name} {name}")
        rows[name] = {
            **enc,
            "decompress_seconds": float(dec["SECONDS"]),
            "sha_ok": True,
        }
        archive.unlink(missing_ok=True)
        shutil.rmtree(outdir, ignore_errors=True)
    oracle = min(FULL, key=lambda k: (rows[k]["bytes"], list(FULL).index(k)))
    return rows, oracle


def probe_choice(cli, data, work, idx):
    sample = work / f"probe_{idx:02d}.bin"
    sample.write_bytes(stratified_2m(data))
    rows = {}
    for name, extra in FULL.items():
        archive = work / f"probe_{idx:02d}_{name}.kpf"
        rows[name] = compress(cli, sample, archive, extra)
        archive.unlink(missing_ok=True)
    sample.unlink(missing_ok=True)
    grain = min(("grain4", "grain8"), key=lambda k: (rows[k]["bytes"], 0 if k == "grain4" else 1))
    choice = grain if rows[grain]["bytes"] < rows["adaptive"]["bytes"] else "adaptive"
    return choice, rows


def policy_summary(records, field):
    raw = sum(r["raw_bytes"] for r in records)
    adaptive = sum(r["full"]["adaptive"]["bytes"] for r in records)
    oracle = sum(r["full"][r["oracle"]]["bytes"] for r in records)
    selected = 0
    harmful = []
    choices = Counter()
    for r in records:
        choice = r[field]
        choices[choice] += 1
        b = r["full"][choice]["bytes"]
        selected += b
        delta = b - r["full"]["adaptive"]["bytes"]
        if delta > 0:
            harmful.append({"file": r["file"], "choice": choice, "delta": delta})
    available = adaptive - oracle
    gain = adaptive - selected
    return {
        "policy": field,
        "raw_bytes": raw,
        "adaptive_bytes": adaptive,
        "oracle_bytes": oracle,
        "selected_bytes": selected,
        "selected_ratio": selected / raw,
        "gain_vs_adaptive": gain,
        "oracle_available_gain": available,
        "oracle_capture": gain / available if available else 1.0,
        "regret_bytes": selected - oracle,
        "harmful_count": len(harmful),
        "harmful": harmful,
        "choices": dict(sorted(choices.items())),
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp118c_grain_holdout.py <kephir2_native_k75_cli>")
    cli = Path(sys.argv[1]).resolve()
    if not cli.is_file():
        raise SystemExit(f"CLI not found: {cli}")

    root = Path("exp118c_holdout")
    work = Path("exp118c_work")
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    root.mkdir(parents=True)
    work.mkdir(parents=True)

    files = build_cases(root)
    records = []
    for idx, src in enumerate(files):
        data = src.read_bytes()
        features = cheap_features(data)
        full, oracle = measure_full(cli, src, work, idx)
        pchoice, probe_rows = probe_choice(cli, data, work, idx)
        fchoice = feature_choice(features)
        record = {
            "file": src.stem,
            "raw_bytes": len(data),
            "features": features,
            "full": full,
            "oracle": oracle,
            "probe_choice": pchoice,
            "feature_choice": fchoice,
            "probe_sample": probe_rows,
        }
        records.append(record)
        print(
            "EXP118C_FILE", record["file"],
            "RAW", len(data),
            "ADAPT", full["adaptive"]["bytes"],
            "G4", full["grain4"]["bytes"],
            "G8", full["grain8"]["bytes"],
            "ORACLE", oracle,
            "PROBE", pchoice,
            "FEATURE", fchoice,
            "H", round(features["entropy"], 6),
            "SPREAD", round(features["quarter_entropy_spread"], 6),
            flush=True,
        )

    probe = policy_summary(records, "probe_choice")
    feature = policy_summary(records, "feature_choice")
    result = {
        "experiment": "EXP-118C",
        "holdout_frozen_before_measurement": True,
        "frozen_probe_policy": "2MiB four-way stratified sample; choose best grain only if sample archive is smaller than adaptive",
        "frozen_feature_policy": "size>=2MiB and (H<6.4 or (H<7.0 and quarter-spread<0.20)) => grain8, else adaptive",
        "files": records,
        "probe": probe,
        "feature": feature,
    }
    Path("exp118c_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))

    print(
        "EXP118C_POLICY probe",
        "GAIN", probe["gain_vs_adaptive"],
        "REGRET", probe["regret_bytes"],
        "HARM", probe["harmful_count"],
        "CAPTURE", probe["oracle_capture"],
        flush=True,
    )
    print(
        "EXP118C_POLICY feature",
        "GAIN", feature["gain_vs_adaptive"],
        "REGRET", feature["regret_bytes"],
        "HARM", feature["harmful_count"],
        "CAPTURE", feature["oracle_capture"],
        flush=True,
    )
    print("EXP118C_COMPLETE", flush=True)

    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
