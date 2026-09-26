#!/usr/bin/env python3
"""
EXP-97 — Current Native KEPHIR vs General-Purpose Compressors

Fairness:
- canonical 12-file Silesia corpus;
- each file compressed independently;
- single-thread competitor modes where supported;
- 3 timed repetitions, median per file;
- full archive/container bytes are counted;
- every decompressed file must match SHA-256 of the source;
- lower ratio is better; higher MB/s is better.

This benchmark intentionally measures the current production-facing KPF1
single-file path rather than an internal raw backend blob.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

ROOT=Path.cwd()
FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]
REPEATS=3


def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def run_timed(command, *, cwd=None, stdout_path=None):
    t0=time.perf_counter()
    if stdout_path is None:
        subprocess.run(
            command,check=True,cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        with open(stdout_path,"wb") as out:
            subprocess.run(
                command,check=True,cwd=cwd,
                stdout=out,
                stderr=subprocess.DEVNULL,
            )
    return time.perf_counter()-t0


def med3(fn):
    values=[fn() for _ in range(REPEATS)]
    return statistics.median(values),values


def tool_version(command):
    try:
        p=subprocess.run(
            command,text=True,capture_output=True,check=False,timeout=10
        )
        text=(p.stdout+"\n"+p.stderr).strip()
        return text.splitlines()[0] if text else "unknown"
    except Exception as exc:
        return "unavailable: "+repr(exc)


def verify(decoded, source_hash, label):
    if not decoded.is_file():
        raise RuntimeError(f"{label}: decoded output missing: {decoded}")
    got=sha256(decoded)
    if got!=source_hash:
        raise RuntimeError(
            f"{label}: SHA mismatch expected={source_hash} got={got}"
        )


def benchmark_native(cli, corpus, out):
    total_raw=0
    total_size=0
    comp_total=0.0
    dec_total=0.0
    per_file=[]

    for name in FILES:
        src=corpus/name
        raw=src.stat().st_size
        src_hash=sha256(src)
        archive=out/f"{name}.kephir.kpf"

        def compress_once():
            if archive.exists():
                archive.unlink()
            return run_timed([str(cli),"c",str(src),str(archive)])

        cmed,cruns=med3(compress_once)
        size=archive.stat().st_size

        def decompress_once():
            ddir=out/f"{name}.kephir.dec"
            if ddir.exists():
                shutil.rmtree(ddir)
            dt=run_timed([str(cli),"d",str(archive),str(ddir)])
            verify(ddir/name,src_hash,"KEPHIR "+name)
            shutil.rmtree(ddir)
            return dt

        dmed,druns=med3(decompress_once)

        total_raw+=raw
        total_size+=size
        comp_total+=cmed
        dec_total+=dmed
        per_file.append({
            "file":name,"raw_bytes":raw,"archive_bytes":size,
            "ratio":size/raw,
            "comp_median_s":cmed,"dec_median_s":dmed,
            "comp_runs_s":cruns,"dec_runs_s":druns,
        })

    return {
        "codec":"KEPHIR 2 Native EXP-95",
        "family":"KEPHIR",
        "raw_bytes":total_raw,
        "archive_bytes":total_size,
        "ratio":total_size/total_raw,
        "comp_seconds":comp_total,
        "dec_seconds":dec_total,
        "comp_MBps":total_raw/1e6/comp_total,
        "dec_MBps":total_raw/1e6/dec_total,
        "sha_all_pass":True,
        "per_file":per_file,
    }


def benchmark_stream_codec(
    name,family,ext,corpus,out,compress_cmd,decompress_cmd,
    *,compress_cwd=False,decompress_cwd=False):

    total_raw=0
    total_size=0
    comp_total=0.0
    dec_total=0.0
    per_file=[]

    safe="".join(ch if ch.isalnum() else "_" for ch in name)

    for filename in FILES:
        src=corpus/filename
        raw=src.stat().st_size
        src_hash=sha256(src)
        archive=out/f"{filename}.{safe}.{ext}"
        decoded=out/f"{filename}.{safe}.decoded"

        def compress_once():
            if archive.exists():
                archive.unlink()
            cmd,stdout=compress_cmd(src,archive)
            cwd=src.parent if compress_cwd else None
            return run_timed(
                cmd,cwd=cwd,
                stdout_path=archive if stdout else None
            )

        cmed,cruns=med3(compress_once)
        if not archive.is_file():
            raise RuntimeError(f"{name}: archive missing for {filename}")
        size=archive.stat().st_size

        def decompress_once():
            if decoded.exists():
                decoded.unlink()
            cmd,stdout=decompress_cmd(archive,decoded,filename)
            cwd=src.parent if decompress_cwd else None
            dt=run_timed(
                cmd,cwd=cwd,
                stdout_path=decoded if stdout else None
            )
            verify(decoded,src_hash,f"{name} {filename}")
            return dt

        dmed,druns=med3(decompress_once)
        if decoded.exists():
            decoded.unlink()

        total_raw+=raw
        total_size+=size
        comp_total+=cmed
        dec_total+=dmed
        per_file.append({
            "file":filename,"raw_bytes":raw,"archive_bytes":size,
            "ratio":size/raw,
            "comp_median_s":cmed,"dec_median_s":dmed,
            "comp_runs_s":cruns,"dec_runs_s":druns,
        })

    return {
        "codec":name,
        "family":family,
        "raw_bytes":total_raw,
        "archive_bytes":total_size,
        "ratio":total_size/total_raw,
        "comp_seconds":comp_total,
        "dec_seconds":dec_total,
        "comp_MBps":total_raw/1e6/comp_total,
        "dec_MBps":total_raw/1e6/dec_total,
        "sha_all_pass":True,
        "per_file":per_file,
    }


def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp97_current_competitor_benchmark.py "
            "/path/to/kephir2_native_k75_cli"
        )

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    if not cli.exists():
        raise SystemExit("KEPHIR CLI missing: "+str(cli))
    if not corpus.exists():
        raise SystemExit("canonical Silesia missing")

    out=ROOT/"exp97_out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    rows=[]
    rows.append(benchmark_native(cli,corpus,out))

    # zstd — explicitly single-thread.
    for level in (1,3,9,19):
        rows.append(benchmark_stream_codec(
            f"Zstd -{level}","Zstd","zst",corpus,out,
            lambda p,o,l=level:(
                ["zstd",f"-{l}","-T1","-q","-f",str(p),"-o",str(o)],False),
            lambda a,d,n:(
                ["zstd","-d","-q","-f",str(a),"-o",str(d)],False),
        ))

    # xz/LZMA2 — single-thread.
    for label,level,extra in (
        ("XZ/LZMA2 -6","-6",[]),
        ("XZ/LZMA2 -9e","-9e",[]),
    ):
        rows.append(benchmark_stream_codec(
            label,"LZMA2","xz",corpus,out,
            lambda p,o,l=level,e=extra:(
                ["xz",l,"-T1","-c",str(p)],True),
            lambda a,d,n:(
                ["xz","-d","-c",str(a)],True),
        ))

    # Brotli CLI is single-threaded.
    for level in (5,11):
        rows.append(benchmark_stream_codec(
            f"Brotli q{level}","Brotli","br",corpus,out,
            lambda p,o,l=level:(
                ["brotli","-q",str(l),"-f",str(p),"-o",str(o)],False),
            lambda a,d,n:(
                ["brotli","-d","-f",str(a),"-o",str(d)],False),
        ))

    # 7-Zip LZMA2; force one thread and archive only basename for fair output.
    for mx in (5,9):
        rows.append(benchmark_stream_codec(
            f"7-Zip/LZMA2 mx{mx}","7-Zip LZMA2","7z",corpus,out,
            lambda p,o,m=mx:(
                ["7z","a","-bd","-y",f"-mx={m}","-m0=lzma2","-mmt=1",
                 str(o.resolve()),p.name],False),
            lambda a,d,n:(
                ["7z","x","-so",str(a.resolve()),n],True),
            compress_cwd=True,
            decompress_cwd=True,
        ))

    rows.append(benchmark_stream_codec(
        "Gzip/Deflate -9","Deflate","gz",corpus,out,
        lambda p,o:(["gzip","-9","-c",str(p)],True),
        lambda a,d,n:(["gzip","-d","-c",str(a)],True),
    ))

    rows.append(benchmark_stream_codec(
        "Bzip2 -9","Bzip2","bz2",corpus,out,
        lambda p,o:(["bzip2","-9","-c",str(p)],True),
        lambda a,d,n:(["bzip2","-d","-c",str(a)],True),
    ))

    rows.append(benchmark_stream_codec(
        "LZ4 default","LZ4","lz4",corpus,out,
        lambda p,o:(["lz4","-q","-f",str(p),str(o)],False),
        lambda a,d,n:(["lz4","-d","-q","-f",str(a),str(d)],False),
    ))

    rows.append(benchmark_stream_codec(
        "LZ4 HC -9","LZ4","lz4",corpus,out,
        lambda p,o:(["lz4","-q","-f","-9",str(p),str(o)],False),
        lambda a,d,n:(["lz4","-d","-q","-f",str(a),str(d)],False),
    ))

    versions={
        "kephir":"2.0-dev-native / EXP-95",
        "zstd":tool_version(["zstd","--version"]),
        "xz":tool_version(["xz","--version"]),
        "brotli":tool_version(["brotli","--version"]),
        "7z":tool_version(["7z"]),
        "gzip":tool_version(["gzip","--version"]),
        "bzip2":tool_version(["bzip2","--help"]),
        "lz4":tool_version(["lz4","--version"]),
    }

    for r in rows:
        assert r["raw_bytes"]==211938580
        assert r["sha_all_pass"]

    by_ratio=sorted(rows,key=lambda r:r["ratio"])
    by_comp=sorted(rows,key=lambda r:r["comp_MBps"],reverse=True)
    by_dec=sorted(rows,key=lambda r:r["dec_MBps"],reverse=True)

    result={
        "experiment":"EXP-97",
        "corpus":"Silesia canonical 12 files",
        "raw_bytes":211938580,
        "repeats":REPEATS,
        "fairness":"single-thread where supported; median-of-3 per file",
        "versions":versions,
        "rows":rows,
        "ranking_ratio":[r["codec"] for r in by_ratio],
        "ranking_comp_speed":[r["codec"] for r in by_comp],
        "ranking_dec_speed":[r["codec"] for r in by_dec],
    }

    Path("exp97_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP97_VERSIONS",json.dumps(versions,sort_keys=True),flush=True)
    print("EXP97_SUMMARY",flush=True)
    for r in by_ratio:
        print(
            "EXP97_ROW",
            r["codec"],
            "BYTES",r["archive_bytes"],
            "RATIO",r["ratio"],
            "COMP_MBPS",r["comp_MBps"],
            "DEC_MBPS",r["dec_MBps"],
            "SHA",r["sha_all_pass"],
            flush=True,
        )
    print("EXP97_SHA_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
