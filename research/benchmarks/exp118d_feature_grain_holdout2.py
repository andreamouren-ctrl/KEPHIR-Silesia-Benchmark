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


def feature_v2(f):
    # Frozen before EXP-118D. Only change from v1 is the extreme-spread veto.
    if f["bytes"] < 2 * MiB:
        return "adaptive"
    if f["quarter_entropy_spread"] >= 6.0:
        return "adaptive"
    if f["entropy"] < 6.4:
        return "grain8"
    if f["entropy"] < 7.0 and f["quarter_entropy_spread"] < 0.20:
        return "grain8"
    return "adaptive"


def feature_v1(f):
    if f["bytes"] >= 2 * MiB and (
        f["entropy"] < 6.4
        or (f["entropy"] < 7.0 and f["quarter_entropy_spread"] < 0.20)
    ):
        return "grain8"
    return "adaptive"


def random_pool_block(pool_size, seed, block=64 * KiB):
    rng = random.Random(seed)
    return bytes(rng.randrange(pool_size) for _ in range(block))


def pool_stream(pool_size, size, seed):
    return repeat(random_pool_block(pool_size, seed), size)


def four_quarters(pool_sizes, size, seed):
    q = size // 4
    out = bytearray()
    for i, pool in enumerate(pool_sizes):
        out.extend(pool_stream(pool, q, seed + i))
    if len(out) < size:
        out.extend(pool_stream(pool_sizes[-1], size - len(out), seed + 99))
    return bytes(out)


def build_cases(root):
    root.mkdir(parents=True, exist_ok=True)
    cases = {}
    rng = random.Random(118D if False else 11840)

    cases["extreme_zero_to_random_8m"] = (
        bytes(2 * MiB)
        + repeat(b"ABCD", 2 * MiB)
        + pool_stream(64, 2 * MiB, 11841)
        + random.Random(11842).randbytes(2 * MiB)
    )
    cases["moderate_entropy_ramp_8m"] = four_quarters([2, 4, 16, 64], 8 * MiB, 11850)
    cases["steep_entropy_ramp_8m"] = four_quarters([2, 8, 64, 256], 8 * MiB, 11860)
    cases["mid_entropy_ramp_8m"] = four_quarters([8, 16, 32, 64], 8 * MiB, 11870)
    cases["stable_pool16_6m"] = pool_stream(16, 6 * MiB, 11880)
    cases["stable_pool32_6m"] = pool_stream(32, 6 * MiB, 11881)
    cases["stable_pool64_6m"] = pool_stream(64, 6 * MiB, 11882)
    cases["stable_pool128_6m"] = pool_stream(128, 6 * MiB, 11883)
    cases["stable_dna_8m"] = repeat(b"ACGTTGCAACGTGGTACCAT", 8 * MiB)
    cases["stable_numeric_6m"] = repeat(
        b"000001,000144,000289,000576,001024,001600,002304,003136\n", 6 * MiB
    )
    block64 = random.Random(11890).randbytes(64 * KiB)
    block1m = random.Random(11891).randbytes(MiB)
    cases["repeat_random64k_8m"] = repeat(block64, 8 * MiB)
    cases["repeat_random1m_8m"] = repeat(block1m, 8 * MiB)
    cases["alternating_zero_random_8m"] = b"".join(
        bytes(512 * KiB) if i % 2 == 0 else random.Random(11900 + i).randbytes(512 * KiB)
        for i in range(16)
    )
    cases["random_with_sparse_zero_runs_8m"] = bytearray(random.Random(11920).randbytes(8 * MiB))
    z = cases["random_with_sparse_zero_runs_8m"]
    for off in range(0, len(z), 512 * KiB):
        z[off:off + 16 * KiB] = bytes(min(16 * KiB, len(z) - off))
    cases["random_with_sparse_zero_runs_8m"] = bytes(z)
    cases["four_text_families_8m"] = (
        repeat(b"plain prose words and spaces in sentences.\n", 2 * MiB)
        + repeat(b"def function(x): return (x * 17) ^ (x >> 2)\n", 2 * MiB)
        + repeat(b"<entry key=\"value\"><node>markup</node></entry>\n", 2 * MiB)
        + repeat(b"000001|000002|000003|000005|000008|000013|\n", 2 * MiB)
    )
    cases["boundary_below_2m"] = repeat(b"boundary low entropy\n", 2 * MiB - 1)
    cases["boundary_above_2m"] = repeat(b"boundary low entropy\n", 2 * MiB + 1)
    cases["incompressible_8m"] = random.Random(11930).randbytes(8 * MiB)

    for name, data in cases.items():
        (root / f"{name}.bin").write_bytes(data)
    return sorted(root.glob("*.bin"))


def compress(cli, src, archive, extra):
    r = run([str(cli), "c", str(src), str(archive), "4", *extra])
    return {"bytes": int(r["OUTPUT_BYTES"]), "seconds": float(r["SECONDS"])}


def measure(cli, src, work, idx):
    source_sha = sha256(src)
    full = {}
    for name, extra in FULL.items():
        archive = work / f"{idx:02d}_{name}.kpf"
        outdir = work / f"{idx:02d}_{name}_out"
        shutil.rmtree(outdir, ignore_errors=True)
        enc = compress(cli, src, archive, extra)
        dec = run([str(cli), "d", str(archive), str(outdir), "4"])
        restored = outdir / src.name
        ok = restored.is_file() and sha256(restored) == source_sha
        if not ok:
            raise RuntimeError(f"roundtrip failure {src.name} {name}")
        full[name] = {
            **enc,
            "decompress_seconds": float(dec["SECONDS"]),
            "sha_ok": True,
        }
        archive.unlink(missing_ok=True)
        shutil.rmtree(outdir, ignore_errors=True)

    oracle = min(FULL, key=lambda k: (full[k]["bytes"], list(FULL).index(k)))
    data = src.read_bytes()
    f = cheap_features(data)
    return {
        "file": src.stem,
        "raw_bytes": len(data),
        "features": f,
        "full": full,
        "oracle": oracle,
        "v1_choice": feature_v1(f),
        "v2_choice": feature_v2(f),
    }


def summarize(rows, field):
    raw = sum(r["raw_bytes"] for r in rows)
    adaptive = sum(r["full"]["adaptive"]["bytes"] for r in rows)
    oracle = sum(r["full"][r["oracle"]]["bytes"] for r in rows)
    selected = 0
    harmful = []
    for r in rows:
        choice = r[field]
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
        "gain_vs_adaptive": gain,
        "regret_bytes": selected - oracle,
        "oracle_capture": gain / available if available else 1.0,
        "harmful_count": len(harmful),
        "harmful": harmful,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp118d_feature_grain_holdout2.py <kephir2_native_k75_cli>")
    cli = Path(sys.argv[1]).resolve()
    root = Path("exp118d_holdout")
    work = Path("exp118d_work")
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    root.mkdir(parents=True)
    work.mkdir(parents=True)

    rows = []
    for idx, src in enumerate(build_cases(root)):
        r = measure(cli, src, work, idx)
        rows.append(r)
        print(
            "EXP118D_FILE", r["file"],
            "RAW", r["raw_bytes"],
            "ADAPT", r["full"]["adaptive"]["bytes"],
            "G4", r["full"]["grain4"]["bytes"],
            "G8", r["full"]["grain8"]["bytes"],
            "ORACLE", r["oracle"],
            "V1", r["v1_choice"],
            "V2", r["v2_choice"],
            "H", round(r["features"]["entropy"], 6),
            "SPREAD", round(r["features"]["quarter_entropy_spread"], 6),
            flush=True,
        )

    v1 = summarize(rows, "v1_choice")
    v2 = summarize(rows, "v2_choice")
    result = {
        "experiment": "EXP-118D",
        "v2_frozen_before_measurement": True,
        "v2_rule": "size>=2MiB AND quarter-spread<6.0 AND (H<6.4 OR (H<7.0 AND quarter-spread<0.20)) => grain8; else adaptive",
        "files": rows,
        "v1": v1,
        "v2": v2,
    }
    Path("exp118d_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    for name, p in (("v1", v1), ("v2", v2)):
        print(
            "EXP118D_POLICY", name,
            "GAIN", p["gain_vs_adaptive"],
            "REGRET", p["regret_bytes"],
            "HARM", p["harmful_count"],
            "CAPTURE", p["oracle_capture"],
            flush=True,
        )
    print("EXP118D_COMPLETE", flush=True)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
