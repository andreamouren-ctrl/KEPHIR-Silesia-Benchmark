#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import random
import shutil
import struct
import subprocess
import time
from pathlib import Path

from kstream_pcm_frontend import encode_file, decode_file


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_pcm(path: Path, seconds=12, rate=48000):
    rng = random.Random(0x4B4550484952)
    out = []
    total = seconds * rate

    for n in range(total):
        t = n / rate
        # Correlated stereo program: tones, slow modulation, transients and low deterministic noise.
        carrier = (
            0.46 * math.sin(2 * math.pi * 220 * t)
            + 0.21 * math.sin(2 * math.pi * 440 * t + 0.17)
            + 0.10 * math.sin(2 * math.pi * (660 + 20 * math.sin(2 * math.pi * 0.31 * t)) * t)
        )
        env = 0.55 + 0.45 * math.sin(2 * math.pi * 0.67 * t) ** 2
        transient = 0.0
        if n % (rate // 2) < 160:
            transient = 0.24 * math.exp(-(n % (rate // 2)) / 45.0)
        noise_l = (rng.random() * 2.0 - 1.0) * 0.012
        noise_r = (rng.random() * 2.0 - 1.0) * 0.012
        l = max(-0.999, min(0.999, carrier * env + transient + noise_l))
        r = max(-0.999, min(0.999, carrier * 0.92 * env - transient * 0.35 + noise_r))
        out.extend((int(l * 30000), int(r * 30000)))

    path.write_bytes(struct.pack("<" + "h" * len(out), *out))


def run_kephir(exe: Path, src: Path, work: Path, tag: str, threads: int):
    arc = work / f"{tag}.aur"
    dec = work / f"dec_{tag}"
    if arc.exists():
        arc.unlink()
    if dec.exists():
        shutil.rmtree(dec)

    t0 = time.perf_counter()
    subprocess.run(
        [str(exe), "cp", str(src), str(arc), str(threads), "6.55", "9.42", "1.20"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    enc_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    subprocess.run(
        [str(exe), "dp", str(arc), str(dec), str(threads)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dec_s = time.perf_counter() - t0

    restored = dec / src.name
    if sha(restored) != sha(src):
        raise SystemExit(f"KEPHIR SHA FAIL: {tag}")

    return {
        "archive_bytes": arc.stat().st_size,
        "encode_seconds": enc_s,
        "decode_seconds": dec_s,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kephir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("streaming/ks01_out"))
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()

    exe = args.kephir.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    raw = out / "ks01_program_s16le_stereo_48k.raw"
    generate_pcm(raw)
    raw_sha = sha(raw)
    raw_bytes = raw.stat().st_size

    direct = run_kephir(exe, raw, out, "direct_pcm", args.threads)
    rows = []

    for block_ms in (5, 10, 20, 40):
        front = out / f"ks01_{block_ms}ms.ksp"
        restored = out / f"ks01_{block_ms}ms.restored.raw"

        t0 = time.perf_counter()
        encode_file(raw, front, channels=2, rate=48000, block_ms=block_ms)
        frontend_enc_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        decode_file(front, restored)
        frontend_dec_s = time.perf_counter() - t0

        if sha(restored) != raw_sha:
            raise SystemExit(f"FRONTEND SHA FAIL: {block_ms} ms")

        backend = run_kephir(exe, front, out, f"frontend_{block_ms}ms", args.threads)
        rows.append({
            "block_ms": block_ms,
            "raw_bytes": raw_bytes,
            "frontend_bytes": front.stat().st_size,
            "direct_kephir_bytes": direct["archive_bytes"],
            "frontend_plus_kephir_bytes": backend["archive_bytes"],
            "delta_bytes_vs_direct": backend["archive_bytes"] - direct["archive_bytes"],
            "delta_percent_vs_direct": 100.0 * (backend["archive_bytes"] - direct["archive_bytes"]) / direct["archive_bytes"],
            "frontend_encode_seconds": frontend_enc_s,
            "frontend_decode_seconds": frontend_dec_s,
            "kephir_encode_seconds": backend["encode_seconds"],
            "kephir_decode_seconds": backend["decode_seconds"],
            "sha_ok": True,
        })

    result = {
        "experiment": "KS-01 PCM reversible frontend smoke benchmark",
        "baseline": "KEPHIR EXP-33H DIST-TOPO-AGGR",
        "source": {
            "type": "deterministic synthetic stereo s16le",
            "rate": 48000,
            "channels": 2,
            "raw_bytes": raw_bytes,
            "sha256": raw_sha,
        },
        "direct_kephir": direct,
        "rows": rows,
        "note": "Synthetic smoke test only; no media-quality claim is permitted from this corpus.",
    }

    p = out / "ks01_results.json"
    p.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
