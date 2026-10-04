#!/usr/bin/env python3
"""AUR2 public C-ABI large-archive memory/throughput qualification.

The parent creates a deterministic mixed directory, then launches compression
and extraction in separate child processes so peak RSS is attributable to one
operation. The child talks only to the public kephir2 C ABI via ctypes.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

KEPHIR2_OK = 0
KEPHIR2_PROFILE_AUTO = 0


class Options(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("profile", ctypes.c_int),
        ("workers", ctypes.c_uint32),
        ("verify_integrity", ctypes.c_int),
        ("overwrite_output", ctypes.c_int),
        ("allow_local_experience", ctypes.c_int),
        ("progress_callback", ctypes.c_void_p),
        ("cancel_callback", ctypes.c_void_p),
        ("user_data", ctypes.c_void_p),
    ]


class Result(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("status", ctypes.c_int),
        ("input_bytes", ctypes.c_uint64),
        ("output_bytes", ctypes.c_uint64),
        ("elapsed_seconds", ctypes.c_double),
        ("message", ctypes.c_char * 512),
    ]


def peak_rss_bytes() -> int:
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if not ok:
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.PeakWorkingSetSize)

    import resource
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes. CI qualification currently uses Linux.
    if sys.platform.startswith("linux"):
        value *= 1024
    return value


def load_api(path: Path):
    lib = ctypes.CDLL(str(path))
    lib.kephir2_create.restype = ctypes.c_void_p
    lib.kephir2_destroy.argtypes = [ctypes.c_void_p]
    lib.kephir2_options_init_v1.argtypes = [ctypes.POINTER(Options)]
    lib.kephir2_compress.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(Options),
        ctypes.POINTER(Result),
    ]
    lib.kephir2_compress.restype = ctypes.c_int
    lib.kephir2_extract.argtypes = list(lib.kephir2_compress.argtypes)
    lib.kephir2_extract.restype = ctypes.c_int
    return lib


def make_options(lib) -> Options:
    options = Options()
    lib.kephir2_options_init_v1(ctypes.byref(options))
    options.profile = KEPHIR2_PROFILE_AUTO
    options.workers = 4
    options.verify_integrity = 1
    options.overwrite_output = 1
    options.allow_local_experience = 0
    return options


def child_operation(args: argparse.Namespace) -> int:
    lib = load_api(Path(args.library).resolve())
    engine = lib.kephir2_create()
    if not engine:
        raise RuntimeError("kephir2_create returned null")
    try:
        options = make_options(lib)
        result = Result()
        result.struct_size = ctypes.sizeof(result)
        begin = time.perf_counter()
        if args.mode == "compress":
            status = lib.kephir2_compress(
                engine,
                os.fsencode(args.input),
                os.fsencode(args.archive),
                ctypes.byref(options),
                ctypes.byref(result),
            )
        else:
            status = lib.kephir2_extract(
                engine,
                os.fsencode(args.archive),
                os.fsencode(args.output),
                ctypes.byref(options),
                ctypes.byref(result),
            )
        wall = time.perf_counter() - begin
        message = bytes(result.message).split(b"\0", 1)[0].decode("utf-8", "replace")
        row = {
            "mode": args.mode,
            "status": int(status),
            "input_bytes": int(result.input_bytes),
            "output_bytes": int(result.output_bytes),
            "engine_elapsed_seconds": float(result.elapsed_seconds),
            "wall_seconds": wall,
            "peak_rss_bytes": peak_rss_bytes(),
            "message": message,
        }
        logical = row["input_bytes"] if args.mode == "compress" else row["output_bytes"]
        row["logical_mib_per_s"] = (
            logical / (1024.0 * 1024.0) / wall if wall > 0 else 0.0
        )
        print("AUR2_SCALE_CHILD " + json.dumps(row, sort_keys=True))
        return 0 if status == KEPHIR2_OK else 2
    finally:
        lib.kephir2_destroy(engine)


def write_repeat(path: Path, pattern: bytes, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        remaining = size
        while remaining:
            chunk = pattern[: min(len(pattern), remaining)]
            f.write(chunk)
            remaining -= len(chunk)


def write_prng(path: Path, size: int, seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = seed & 0xFFFFFFFF
    block = bytearray(1024 * 1024)
    remaining = size
    with path.open("wb") as f:
        while remaining:
            n = min(len(block), remaining)
            for i in range(n):
                state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
                block[i] = (state >> 24) & 0xFF
            f.write(memoryview(block)[:n])
            remaining -= n


def prepare_fixture(root: Path, mib: int) -> Path:
    source = root / "source"
    source.mkdir(parents=True, exist_ok=True)
    total = mib * 1024 * 1024
    parts = [total // 4] * 4
    parts[-1] += total - sum(parts)
    write_repeat(
        source / "text" / "prose.txt",
        b"AURORA KEPHIR deterministic large archive qualification text line.\n",
        parts[0],
    )
    write_repeat(
        source / "code" / "source.cpp",
        b"template<class T> T combine(T a,T b){return a+b;} // AUR2\n",
        parts[1],
    )
    write_repeat(
        source / "structured" / "words.bin",
        b"\x00\x00\x01\x00\x04\x00\x10\x00",
        parts[2],
    )
    write_prng(source / "binary" / "random.bin", parts[3], 0xA2202601)
    (source / "empty-dir").mkdir()
    (source / "empty.bin").write_bytes(b"")
    return source


def file_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        out[path.relative_to(root).as_posix()] = h.hexdigest()
    return out


def run_child(script: Path, library: Path, mode: str, root: Path) -> dict:
    archive = root / "scale.aur"
    command = [
        sys.executable,
        str(script),
        "--child",
        "--library",
        str(library),
        "--mode",
        mode,
        "--archive",
        str(archive),
    ]
    if mode == "compress":
        command += ["--input", str(root / "source")]
    else:
        command += ["--output", str(root / "decoded")]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    line = next(
        line for line in completed.stdout.splitlines()
        if line.startswith("AUR2_SCALE_CHILD ")
    )
    return json.loads(line.split(" ", 1)[1])


def parent(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve()
    library = Path(args.library).resolve()
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    rows = []

    for mib in sizes:
        with tempfile.TemporaryDirectory(prefix=f"aur2-scale-{mib}m-") as tmp:
            root = Path(tmp)
            source = prepare_fixture(root, mib)
            expected = file_hashes(source)
            encode = run_child(script, library, "compress", root)
            decode = run_child(script, library, "extract", root)
            actual = file_hashes(root / "decoded")
            if actual != expected:
                raise AssertionError(f"round-trip hash mismatch for {mib} MiB fixture")
            archive_bytes = (root / "scale.aur").stat().st_size
            row = {
                "fixture_mib": mib,
                "logical_bytes": sum((source / p).stat().st_size for p in expected),
                "archive_bytes": archive_bytes,
                "ratio": archive_bytes / max(1, sum((source / p).stat().st_size for p in expected)),
                "encode": encode,
                "decode": decode,
                "sha_all_pass": True,
            }
            rows.append(row)
            print(
                "AUR2_SCALE_ROW",
                mib,
                "MiB",
                "archive", archive_bytes,
                "enc", f"{encode['logical_mib_per_s']:.3f}", "MiB/s",
                "dec", f"{decode['logical_mib_per_s']:.3f}", "MiB/s",
                "enc_peak", encode["peak_rss_bytes"],
                "dec_peak", decode["peak_rss_bytes"],
            )

    result = {
        "schema": 1,
        "library": str(library),
        "rows": rows,
        "all_roundtrips_pass": all(r["sha_all_pass"] for r in rows),
    }
    Path(args.output_json).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if not result["all_roundtrips_pass"]:
        return 3
    # Guard only against catastrophic memory regressions; this benchmark records
    # measurements rather than pretending the still-contiguous K75 stream is fully streaming.
    for row in rows:
        if row["encode"]["peak_rss_bytes"] > 2 * 1024**3:
            raise AssertionError("encode peak RSS exceeded 2 GiB safety ceiling")
        if row["decode"]["peak_rss_bytes"] > 2 * 1024**3:
            raise AssertionError("decode peak RSS exceeded 2 GiB safety ceiling")
    print("AUR2_SCALE_VALIDATION_PASS")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--library", required=True)
    p.add_argument("--sizes", default="16,64")
    p.add_argument("--output-json", default="aur2_scale_results.json")
    p.add_argument("--child", action="store_true")
    p.add_argument("--mode", choices=["compress", "extract"])
    p.add_argument("--input")
    p.add_argument("--archive")
    p.add_argument("--output")
    return p.parse_args()


if __name__ == "__main__":
    ns = parse_args()
    raise SystemExit(child_operation(ns) if ns.child else parent(ns))
