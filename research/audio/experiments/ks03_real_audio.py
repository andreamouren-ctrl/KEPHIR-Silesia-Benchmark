#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from kstream_pcm_frontend import encode_file as encode_varint, decode_file as decode_varint
from kstream_kmrl_frontend import encode_file as encode_kmrl, decode_file as decode_kmrl

OUT = Path("streaming/ks03_out")
RATE = 48000
CHANNELS = 2
BITS = 16
BLOCK_MS = 20
BLOCK_SAMPLES = RATE * BLOCK_MS // 1000


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def timed(cmd, **kwargs):
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, **kwargs)
    return time.perf_counter() - t0


def kephir_roundtrip(exe: Path, src: Path, tag: str):
    arc = OUT / f"{tag}.aur"
    dec = OUT / f"dec_{tag}"
    if arc.exists():
        arc.unlink()
    if dec.exists():
        shutil.rmtree(dec)

    enc_s = timed(
        [str(exe.resolve()), "cp", str(src), str(arc), "6", "6.55", "9.42", "1.20"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    dec_s = timed(
        [str(exe.resolve()), "dp", str(arc), str(dec), "6"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    restored = dec / src.name
    if sha(restored) != sha(src):
        raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size, enc_s, dec_s


def frontend_kephir(exe, raw, tag, enc_fn, dec_fn):
    front = OUT / f"{tag}.front"
    restored = OUT / f"{tag}.restored.raw"

    t0 = time.perf_counter()
    enc_fn(raw, front, channels=CHANNELS, rate=RATE, block_ms=BLOCK_MS)
    front_enc_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    dec_fn(front, restored)
    front_dec_s = time.perf_counter() - t0

    if sha(restored) != sha(raw):
        raise SystemExit(f"FRONTEND SHA FAIL {tag}")

    size, kenc, kdec = kephir_roundtrip(exe, front, tag)
    return {
        "codec": tag,
        "bytes": size,
        "frontend_bytes": front.stat().st_size,
        "encode_seconds": front_enc_s + kenc,
        "decode_seconds": front_dec_s + kdec,
        "frontend_encode_seconds": front_enc_s,
        "frontend_decode_seconds": front_dec_s,
        "backend_encode_seconds": kenc,
        "backend_decode_seconds": kdec,
        "sha_ok": True,
    }


def flac_roundtrip(raw: Path):
    out = OUT / "flac_20ms.flac"
    restored = OUT / "flac_20ms.restored.raw"
    if out.exists():
        out.unlink()
    if restored.exists():
        restored.unlink()

    enc_cmd = [
        "flac", "-5", "-f", "-s",
        f"--blocksize={BLOCK_SAMPLES}",
        "--no-padding", "--no-seektable",
        "--force-raw-format",
        "--endian=little", "--sign=signed",
        f"--channels={CHANNELS}", f"--bps={BITS}", f"--sample-rate={RATE}",
        "-o", str(out), str(raw),
    ]
    enc_s = timed(enc_cmd)

    dec_cmd = [
        "flac", "-d", "-f", "-s",
        "--force-raw-format",
        "--endian=little", "--sign=signed",
        "-o", str(restored), str(out),
    ]
    dec_s = timed(dec_cmd)

    if sha(restored) != sha(raw):
        raise SystemExit("FLAC SHA FAIL")

    return {
        "codec": "FLAC5_BLOCK960",
        "bytes": out.stat().st_size,
        "encode_seconds": enc_s,
        "decode_seconds": dec_s,
        "sha_ok": True,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--kephir", type=Path, default=Path("./kephir33"))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    raw = args.raw.resolve()
    if raw.stat().st_size % (CHANNELS * 2):
        raise SystemExit("raw input is not complete stereo s16le")

    raw_bytes = raw.stat().st_size
    raw_hash = sha(raw)
    duration_s = raw_bytes / (RATE * CHANNELS * 2)

    direct_bytes, direct_enc, direct_dec = kephir_roundtrip(args.kephir, raw, "DIRECT_PCM")
    rows = [
        {
            "codec": "DIRECT_KEPHIR_EXP33H",
            "bytes": direct_bytes,
            "encode_seconds": direct_enc,
            "decode_seconds": direct_dec,
            "sha_ok": True,
        },
        frontend_kephir(args.kephir, raw, "KS01_VARINT_20", encode_varint, decode_varint),
        frontend_kephir(args.kephir, raw, "KMRL0_20", encode_kmrl, decode_kmrl),
        flac_roundtrip(raw),
    ]

    for r in rows:
        r["ratio_to_pcm_percent"] = 100.0 * r["bytes"] / raw_bytes
        r["bits_per_sample"] = 8.0 * r["bytes"] / (raw_bytes / 2.0)
        r["encode_realtime_x"] = duration_s / r["encode_seconds"] if r["encode_seconds"] else None
        r["decode_realtime_x"] = duration_s / r["decode_seconds"] if r["decode_seconds"] else None

    result = {
        "experiment": "KS-03 real-media audio checkpoint",
        "source": {
            "origin": "Xiph.org Sintel trailer audio, decoded/resampled to benchmark PCM",
            "profile": "stereo s16le 48kHz",
            "bytes": raw_bytes,
            "duration_seconds": duration_s,
            "sha256": raw_hash,
        },
        "stream_block_ms": BLOCK_MS,
        "flac_block_samples": BLOCK_SAMPLES,
        "rows": rows,
        "interpretation_rule": "Compare the exact same derived PCM. This checkpoint tests lossless compression only; no lossy/perceptual claim is permitted.",
    }
    (OUT / "ks03_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
