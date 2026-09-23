#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from ks01_pcm_bench import generate_pcm
from kstream_pcm_frontend import encode_file as encode_varint, decode_file as decode_varint
from kstream_kmrl_frontend import encode_file as encode_kmrl, decode_file as decode_kmrl

ROOT = Path("streaming/ks02_out")


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_kephir(exe: Path, src: Path, tag: str):
    arc = ROOT / f"{tag}.aur"
    dec = ROOT / f"dec_{tag}"
    if arc.exists():
        arc.unlink()
    if dec.exists():
        shutil.rmtree(dec)

    t0 = time.perf_counter()
    subprocess.run([str(exe.resolve()), "cp", str(src), str(arc), "6", "6.55", "9.42", "1.20"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    enc_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    subprocess.run([str(exe.resolve()), "dp", str(arc), str(dec), "6"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dec_s = time.perf_counter() - t0

    restored = dec / src.name
    if sha(restored) != sha(src):
        raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size, enc_s, dec_s


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    raw = ROOT / "ks02_source_s16le_stereo_48k.raw"
    generate_pcm(raw, seconds=12, rate=48000)
    raw_sha = sha(raw)
    raw_bytes = raw.stat().st_size

    variants = [
        ("KS01_VARINT_20", encode_varint, decode_varint, 20),
        ("KMRL0_5", encode_kmrl, decode_kmrl, 5),
        ("KMRL0_20", encode_kmrl, decode_kmrl, 20),
        ("KMRL0_40", encode_kmrl, decode_kmrl, 40),
    ]

    exe = Path("./kephir33")
    rows = []
    for tag, enc, dec, block_ms in variants:
        front = ROOT / f"{tag}.bin"
        restored = ROOT / f"{tag}.restored.raw"

        t0 = time.perf_counter()
        enc(raw, front, channels=2, rate=48000, block_ms=block_ms)
        fenc = time.perf_counter() - t0

        t0 = time.perf_counter()
        dec(front, restored)
        fdec = time.perf_counter() - t0

        if sha(restored) != raw_sha:
            raise SystemExit(f"FRONTEND SHA FAIL {tag}")

        kbytes, kenc, kdec = run_kephir(exe, front, tag)
        rows.append({
            "variant": tag,
            "block_ms": block_ms,
            "raw_bytes": raw_bytes,
            "frontend_bytes": front.stat().st_size,
            "kephir_bytes": kbytes,
            "ratio_to_raw_percent": 100.0 * kbytes / raw_bytes,
            "frontend_encode_s": fenc,
            "frontend_decode_s": fdec,
            "kephir_encode_s": kenc,
            "kephir_decode_s": kdec,
            "sha_ok": True,
        })

    baseline = next(r for r in rows if r["variant"] == "KS01_VARINT_20")
    for r in rows:
        r["delta_vs_ks01_bytes"] = r["kephir_bytes"] - baseline["kephir_bytes"]
        r["delta_vs_ks01_percent"] = 100.0 * (r["kephir_bytes"] - baseline["kephir_bytes"]) / baseline["kephir_bytes"]

    result = {
        "experiment": "KS-02 KMRL-0 synthetic checkpoint",
        "backend": "KEPHIR EXP-33H DIST-TOPO-AGGR",
        "source_sha256": raw_sha,
        "source_bytes": raw_bytes,
        "rows": rows,
        "promotion_rule": "KMRL is promoted only if reversible and useful enough to justify real-media testing.",
    }
    (ROOT / "ks02_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
