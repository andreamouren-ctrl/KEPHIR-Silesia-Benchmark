#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MiB = 1024 * 1024
RAW_TOTAL_EXPECTED = 211_938_580
KEPHIR_EXPECTED_BYTES = 60_963_390


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(MiB), b""):
            h.update(block)
    return h.hexdigest()


def run_wall(cmd, stdout=None, cwd=None):
    t0 = time.perf_counter()
    p = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return time.perf_counter() - t0, p


def parse_kv(text):
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def silesia_files():
    root = Path("corpora/silesia")
    files = sorted(p for p in root.iterdir() if p.is_file())
    raw = sum(p.stat().st_size for p in files)
    if raw != RAW_TOTAL_EXPECTED:
        raise RuntimeError(f"unexpected Silesia size: {raw}")
    return files


def sample_stratified(data, budget=2 * MiB):
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


def kephir_compress(cli, src, dst, extra):
    t0 = time.perf_counter()
    p = subprocess.run(
        [str(cli), "c", str(src), str(dst), "4", *extra],
        text=True,
        capture_output=True,
        check=True,
    )
    wall = time.perf_counter() - t0
    kv = parse_kv(p.stdout)
    return wall, int(kv["OUTPUT_BYTES"]), float(kv["SECONDS"])


def kephir_decompress(cli, archive, outdir):
    shutil.rmtree(outdir, ignore_errors=True)
    t0 = time.perf_counter()
    p = subprocess.run(
        [str(cli), "d", str(archive), str(outdir), "4"],
        text=True,
        capture_output=True,
        check=True,
    )
    wall = time.perf_counter() - t0
    kv = parse_kv(p.stdout)
    return wall, float(kv["SECONDS"])


def bench_kephir(cli, files, work):
    candidates = {
        "adaptive": ["adaptive"],
        "grain4": ["4096", "4096", "1"],
        "grain8": ["8192", "8192", "1"],
    }
    total_bytes = 0
    total_encode_wall = 0.0
    total_probe_wall = 0.0
    total_final_encode_wall = 0.0
    total_decode_wall = 0.0
    choices = {k: 0 for k in candidates}
    rows = []

    for i, src in enumerate(files):
        raw = src.read_bytes()
        probe_t0 = time.perf_counter()
        sample = work / f"sample_{i:02d}.bin"
        sample.write_bytes(sample_stratified(raw))
        probe_sizes = {}
        for name, extra in candidates.items():
            arc = work / f"probe_{i:02d}_{name}.kpf"
            wall, size, _ = kephir_compress(cli, sample, arc, extra)
            probe_sizes[name] = size
            arc.unlink(missing_ok=True)
        sample.unlink(missing_ok=True)
        probe_wall = time.perf_counter() - probe_t0
        choice = min(candidates, key=lambda k: (probe_sizes[k], list(candidates).index(k)))

        archive = work / f"kephir_{i:02d}.kpf"
        full_wall, size, full_internal = kephir_compress(cli, src, archive, candidates[choice])
        outdir = work / f"kephir_out_{i:02d}"
        dec_wall, dec_internal = kephir_decompress(cli, archive, outdir)
        restored = outdir / src.name
        if not restored.is_file() or sha256(restored) != sha256(src):
            raise RuntimeError(f"KEPHIR roundtrip failed: {src.name}")

        total_bytes += size
        total_probe_wall += probe_wall
        total_final_encode_wall += full_wall
        total_encode_wall += probe_wall + full_wall
        total_decode_wall += dec_wall
        choices[choice] += 1
        rows.append({
            "file": src.name,
            "choice": choice,
            "bytes": size,
            "probe_wall_seconds": probe_wall,
            "final_encode_wall_seconds": full_wall,
            "decode_wall_seconds": dec_wall,
            "final_internal_seconds": full_internal,
            "decode_internal_seconds": dec_internal,
        })
        archive.unlink(missing_ok=True)
        shutil.rmtree(outdir, ignore_errors=True)

    if total_bytes != KEPHIR_EXPECTED_BYTES:
        raise RuntimeError(
            f"KEPHIR policy drift: {total_bytes} != {KEPHIR_EXPECTED_BYTES}"
        )

    return {
        "name": "KEPHIR2 EXP-118B AUTO",
        "available": True,
        "archive_bytes": total_bytes,
        "ratio": total_bytes / RAW_TOTAL_EXPECTED,
        "compress_seconds": total_encode_wall,
        "compress_MBps": RAW_TOTAL_EXPECTED / 1e6 / total_encode_wall,
        "final_encode_seconds_excluding_probe": total_final_encode_wall,
        "final_encode_MBps_excluding_probe": RAW_TOTAL_EXPECTED / 1e6 / total_final_encode_wall,
        "probe_seconds": total_probe_wall,
        "decompress_seconds": total_decode_wall,
        "decompress_MBps": RAW_TOTAL_EXPECTED / 1e6 / total_decode_wall,
        "choices": choices,
        "rows": rows,
        "notes": "2 MiB stratified probe; real probe cost included in primary compression speed",
    }


def ensure_equal(src, out):
    if not out.is_file() or sha256(src) != sha256(out):
        raise RuntimeError(f"roundtrip mismatch: {src} -> {out}")


def bench_stream_codec(name, files, work, compress_builder, decompress_builder):
    total_bytes = 0
    enc = 0.0
    dec = 0.0
    for i, src in enumerate(files):
        arc = work / f"{name}_{i:02d}.bin"
        out = work / f"{name}_{i:02d}.out"
        with open(arc, "wb") as f:
            dt, _ = run_wall(compress_builder(src), stdout=f)
        enc += dt
        total_bytes += arc.stat().st_size
        with open(out, "wb") as f:
            dt, _ = run_wall(decompress_builder(arc), stdout=f)
        dec += dt
        ensure_equal(src, out)
        arc.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    return metric(name, total_bytes, enc, dec)


def bench_file_codec(name, files, work, compress_builder, decompress_builder, archive_suffix):
    total_bytes = 0
    enc = 0.0
    dec = 0.0
    for i, src in enumerate(files):
        arc = work / f"{name}_{i:02d}{archive_suffix}"
        outdir = work / f"{name}_{i:02d}_out"
        shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True)
        dt, _ = run_wall(compress_builder(src, arc))
        enc += dt
        total_bytes += arc.stat().st_size
        dt, _ = run_wall(decompress_builder(arc, outdir))
        dec += dt
        out = outdir / src.name
        ensure_equal(src, out)
        arc.unlink(missing_ok=True)
        shutil.rmtree(outdir, ignore_errors=True)
    return metric(name, total_bytes, enc, dec)


def metric(name, total_bytes, enc, dec):
    return {
        "name": name,
        "available": True,
        "archive_bytes": total_bytes,
        "ratio": total_bytes / RAW_TOTAL_EXPECTED,
        "compress_seconds": enc,
        "compress_MBps": RAW_TOTAL_EXPECTED / 1e6 / enc,
        "decompress_seconds": dec,
        "decompress_MBps": RAW_TOTAL_EXPECTED / 1e6 / dec,
    }


def version(cmd):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        text = (p.stdout + "\n" + p.stderr).strip().splitlines()
        return text[0] if text else "unknown"
    except Exception as e:
        return f"unavailable: {e}"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp119_current_compressor_shootout.py <kephir2_native_k75_cli>")
    cli = Path(sys.argv[1]).resolve()
    files = silesia_files()
    work = Path("exp119_work")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    versions = {
        "gzip": version(["gzip", "--version"]),
        "bzip2": version(["bzip2", "--version"]),
        "xz": version(["xz", "--version"]),
        "zstd": version(["zstd", "--version"]),
        "lz4": version(["lz4", "--version"]),
        "brotli": version(["brotli", "--version"]),
        "7z": version(["7z", "i"]),
        "rar": version(["rar"]),
    }

    results = [bench_kephir(cli, files, work)]

    stream_specs = [
        ("gzip-9", lambda s: ["gzip", "-9", "-c", str(s)], lambda a: ["gzip", "-d", "-c", str(a)]),
        ("bzip2-9", lambda s: ["bzip2", "-9", "-c", str(s)], lambda a: ["bzip2", "-d", "-c", str(a)]),
        ("xz-6", lambda s: ["xz", "-6", "-c", str(s)], lambda a: ["xz", "-d", "-c", str(a)]),
        ("xz-9e", lambda s: ["xz", "-9e", "-c", str(s)], lambda a: ["xz", "-d", "-c", str(a)]),
        ("zstd-1", lambda s: ["zstd", "-1", "-q", "-c", str(s)], lambda a: ["zstd", "-d", "-q", "-c", str(a)]),
        ("zstd-3", lambda s: ["zstd", "-3", "-q", "-c", str(s)], lambda a: ["zstd", "-d", "-q", "-c", str(a)]),
        ("zstd-9", lambda s: ["zstd", "-9", "-q", "-c", str(s)], lambda a: ["zstd", "-d", "-q", "-c", str(a)]),
        ("zstd-19", lambda s: ["zstd", "-19", "-q", "-c", str(s)], lambda a: ["zstd", "-d", "-q", "-c", str(a)]),
        ("lz4", lambda s: ["lz4", "-q", "-f", "-c", str(s)], lambda a: ["lz4", "-q", "-d", "-c", str(a)]),
        ("lz4hc-9", lambda s: ["lz4", "-q", "-9", "-f", "-c", str(s)], lambda a: ["lz4", "-q", "-d", "-c", str(a)]),
        ("brotli-q5", lambda s: ["brotli", "-q", "5", "-c", str(s)], lambda a: ["brotli", "-d", "-c", str(a)]),
        ("brotli-q11", lambda s: ["brotli", "-q", "11", "-c", str(s)], lambda a: ["brotli", "-d", "-c", str(a)]),
    ]
    for name, cb, db in stream_specs:
        print("EXP119_START", name, flush=True)
        results.append(bench_stream_codec(name, files, work, cb, db))
        print("EXP119_DONE", name, results[-1]["ratio"], results[-1]["compress_MBps"], results[-1]["decompress_MBps"], flush=True)

    file_specs = [
        (
            "7z-lzma2-mx5",
            lambda s, a: ["7z", "a", "-bd", "-y", "-t7z", "-m0=lzma2", "-mx=5", str(a), str(s)],
            lambda a, o: ["7z", "x", "-bd", "-y", f"-o{o}", str(a)],
            ".7z",
        ),
        (
            "7z-lzma2-mx9",
            lambda s, a: ["7z", "a", "-bd", "-y", "-t7z", "-m0=lzma2", "-mx=9", str(a), str(s)],
            lambda a, o: ["7z", "x", "-bd", "-y", f"-o{o}", str(a)],
            ".7z",
        ),
        (
            "zip-deflate-9",
            lambda s, a: ["7z", "a", "-bd", "-y", "-tzip", "-mm=Deflate", "-mx=9", str(a), str(s)],
            lambda a, o: ["7z", "x", "-bd", "-y", f"-o{o}", str(a)],
            ".zip",
        ),
    ]
    for name, cb, db, suffix in file_specs:
        print("EXP119_START", name, flush=True)
        results.append(bench_file_codec(name, files, work, cb, db, suffix))
        print("EXP119_DONE", name, results[-1]["ratio"], results[-1]["compress_MBps"], results[-1]["decompress_MBps"], flush=True)

    if shutil.which("rar") and shutil.which("unrar"):
        print("EXP119_START rar5-m5", flush=True)
        try:
            results.append(bench_file_codec(
                "rar5-m5",
                files,
                work,
                lambda s, a: ["rar", "a", "-ma5", "-m5", "-idq", str(a), str(s)],
                lambda a, o: ["unrar", "e", "-inul", "-o+", str(a), str(o) + os.sep],
                ".rar",
            ))
            print("EXP119_DONE rar5-m5", results[-1]["ratio"], results[-1]["compress_MBps"], results[-1]["decompress_MBps"], flush=True)
        except Exception as e:
            results.append({"name": "rar5-m5", "available": False, "error": str(e)})
    else:
        results.append({"name": "rar5-m5", "available": False, "error": "rar/unrar not installed on runner"})

    available = [r for r in results if r.get("available")]
    ranked = sorted(available, key=lambda r: r["ratio"])
    for i, r in enumerate(ranked, 1):
        print(
            "EXP119_RESULT", i, r["name"],
            "BYTES", r["archive_bytes"],
            "RATIO", r["ratio"],
            "COMP_MBPS", r["compress_MBps"],
            "DEC_MBPS", r["decompress_MBps"],
            flush=True,
        )

    result = {
        "experiment": "EXP-119",
        "corpus": "Silesia",
        "raw_bytes": RAW_TOTAL_EXPECTED,
        "measurement": "per-file archives, single runner; compression/decompression wall time",
        "kephir_workers": 4,
        "versions": versions,
        "results": results,
        "ranked_by_ratio": [r["name"] for r in ranked],
    }
    Path("exp119_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    shutil.rmtree(work, ignore_errors=True)
    print("EXP119_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
