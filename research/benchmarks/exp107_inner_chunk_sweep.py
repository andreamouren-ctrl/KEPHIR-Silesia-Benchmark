#!/usr/bin/env python3
"""
EXP-107 — EXP-37 Inner Chunk Size Sweep

Research-only test of the raw EXP-37 backend at 256/512/1024/2048 KiB
internal chunks on canonical Silesia.

Purpose:
Determine whether larger independent backend context is a promising route
before changing K75 parent structure or archive format.

This is NOT a production KEPHIR benchmark.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT=Path.cwd()
FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]
SIZES=[256,512,1024,2048]


def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def main():
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp107_chunk_sweep"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]

    for kib in SIZES:
        exe=ROOT/f"kephir37_{kib}"
        if not exe.exists():
            raise SystemExit(f"missing backend executable {exe}")

        raw_total=0
        arc_total=0
        comp_total=0.0
        dec_total=0.0
        per_file=[]

        for name in FILES:
            src=corpus/name
            arc=work/f"{name}.{kib}.aur"
            out=work/f"out_{kib}_{name}"
            if out.exists():
                shutil.rmtree(out)

            t0=time.perf_counter()
            subprocess.run(
                [str(exe),"cp",str(src),str(arc),"6","6.55","9.42","1.20"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            comp=time.perf_counter()-t0

            t0=time.perf_counter()
            subprocess.run(
                [str(exe),"dp",str(arc),str(out),"6"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            dec=time.perf_counter()-t0

            files=[p for p in out.rglob("*") if p.is_file()]
            if len(files)!=1:
                raise SystemExit(f"unexpected decode output for {name} @ {kib}")
            if sha256(files[0])!=sha256(src):
                raise SystemExit(f"SHA mismatch {name} @ {kib}")

            raw=src.stat().st_size
            ab=arc.stat().st_size
            raw_total+=raw
            arc_total+=ab
            comp_total+=comp
            dec_total+=dec

            per_file.append({
                "file":name,
                "raw_bytes":raw,
                "archive_bytes":ab,
                "ratio":ab/raw,
                "comp_seconds":comp,
                "dec_seconds":dec,
            })

            shutil.rmtree(out)

        row={
            "chunk_kib":kib,
            "raw_bytes":raw_total,
            "archive_bytes":arc_total,
            "ratio":arc_total/raw_total,
            "comp_seconds":comp_total,
            "dec_seconds":dec_total,
            "comp_MBps":raw_total/1e6/comp_total,
            "dec_MBps":raw_total/1e6/dec_total,
            "sha_all_pass":True,
            "per_file":per_file,
        }
        rows.append(row)

        print(
            "EXP107_ROW",
            "CHUNK_KIB",kib,
            "BYTES",arc_total,
            "RATIO",row["ratio"],
            "COMP_MBPS",row["comp_MBps"],
            "DEC_MBPS",row["dec_MBps"],
            "SHA",True,
            flush=True,
        )

    baseline=next(r for r in rows if r["chunk_kib"]==512)
    for r in rows:
        r["bytes_vs_512"]=r["archive_bytes"]-baseline["archive_bytes"]
        r["ratio_delta_vs_512"]=r["ratio"]-baseline["ratio"]

    result={
        "experiment":"EXP-107",
        "purpose":"raw-inner-chunk-size-sweep",
        "note":"research-only raw EXP-37 backend, not production KPF1/K75",
        "rows":rows,
    }
    Path("exp107_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP107_SWEEP_COMPLETE",flush=True)


if __name__=="__main__":
    main()
