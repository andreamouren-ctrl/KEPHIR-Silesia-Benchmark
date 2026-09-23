#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import kstream_kmrl_frontend as kmrl
from ks01_pcm_bench import generate_pcm

ROOT = Path("streaming/ks03_out")


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def serialize_us(mode: int, us):
    classes = [kmrl.residual_class(u) for u in us]
    out = bytearray([mode])
    out.extend(kmrl.pack_classes(classes))

    c0 = [u for u, c in zip(us, classes) if c == 0]
    c1 = [u for u, c in zip(us, classes) if c == 1]
    c2 = [u for u, c in zip(us, classes) if c == 2]
    c3 = [u for u, c in zip(us, classes) if c == 3]

    for i in range(0, len(c0), 2):
        a = c0[i] & 0xF
        b = (c0[i + 1] & 0xF) if i + 1 < len(c0) else 0
        out.append(a | (b << 4))

    out.extend(u & 0xFF for u in c1)
    out.extend(u & 0xFF for u in c2)
    out.extend((u >> 8) & 0xFF for u in c2)
    for shift in (0, 8, 16, 24):
        out.extend((u >> shift) & 0xFF for u in c3)
    return bytes(out)


def topo_hits(buf: bytes):
    # Deliberately mirror the two native recurrence scales used by KEPHIR:
    # 16-wide line and 256-wide plane.
    h16 = sum(1 for i in range(16, len(buf)) if buf[i] == buf[i - 16])
    h256 = sum(1 for i in range(256, len(buf)) if buf[i] == buf[i - 256])
    return h16, h256


def make_encoder(alpha16: float, alpha256: float):
    def encode_component(values):
        candidates = []
        for mode in (0, 1, 2):
            rs = kmrl.residuals_for(values, mode)
            us = [kmrl.zz_enc(r) for r in rs]
            encoded = serialize_us(mode, us)
            h16, h256 = topo_hits(encoded)
            score = len(encoded) - alpha16 * h16 - alpha256 * h256
            candidates.append((score, len(encoded), mode, encoded))
        _, _, _, encoded = min(candidates, key=lambda x: (x[0], x[1], x[2]))
        return encoded
    return encode_component


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
    raw = ROOT / "ks03_source_s16le_stereo_48k.raw"
    generate_pcm(raw, seconds=12, rate=48000)
    raw_sha = sha(raw)
    raw_bytes = raw.stat().st_size
    exe = Path("./kephir33")

    variants = [
        ("KMRL_BASE", 0.0, 0.0),
        ("KMRL_TOPO_LIGHT", 0.06, 0.12),
        ("KMRL_TOPO_STRONG", 0.14, 0.28),
    ]

    rows = []
    original_encoder = kmrl.encode_component
    try:
        for tag, a16, a256 in variants:
            kmrl.encode_component = make_encoder(a16, a256)
            front = ROOT / f"{tag}.kmr"
            restored = ROOT / f"{tag}.restored.raw"

            t0 = time.perf_counter()
            kmrl.encode_file(raw, front, channels=2, rate=48000, block_ms=20)
            fenc = time.perf_counter() - t0

            t0 = time.perf_counter()
            kmrl.decode_file(front, restored)
            fdec = time.perf_counter() - t0

            if sha(restored) != raw_sha:
                raise SystemExit(f"FRONTEND SHA FAIL {tag}")

            kbytes, kenc, kdec = run_kephir(exe, front, tag)
            rows.append({
                "variant": tag,
                "alpha16": a16,
                "alpha256": a256,
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
    finally:
        kmrl.encode_component = original_encoder

    base = rows[0]
    for r in rows:
        r["delta_vs_base_bytes"] = r["kephir_bytes"] - base["kephir_bytes"]
        r["delta_vs_base_percent"] = 100.0 * (r["kephir_bytes"] - base["kephir_bytes"]) / base["kephir_bytes"]

    result = {
        "experiment": "KS-03 topology-aware predictor selection",
        "backend": "KEPHIR EXP-33H DIST-TOPO-AGGR",
        "source_sha256": raw_sha,
        "source_bytes": raw_bytes,
        "rows": rows,
        "promotion_rule": "Promote topology pressure only if final KEPHIR bytes improve while reconstruction remains bit-exact.",
    }
    (ROOT / "ks03_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
