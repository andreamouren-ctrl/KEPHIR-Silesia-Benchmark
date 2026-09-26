#!/usr/bin/env python3
"""
EXP-98 — Bounded Parallel Decode Scaling

Compression stays single-threaded and archive bytes are produced once.
The same KPF1 archives are then decoded with 1/2/4/8/16 workers.

Measures:
- exact archive bytes;
- median-of-3 decode throughput;
- SHA-256 roundtrip for every worker count;
- speedup versus one worker.
"""
from pathlib import Path
import hashlib
import json
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
WORKERS=[1,2,4,8,16]
REPEATS=3

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def parse_cli(text):
    out={}
    for line in text.splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            out[k.strip()]=v.strip()
    return out

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp98_parallel_decode.py /path/to/kephir2_native_k75_cli")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    if not cli.exists():
        raise SystemExit("missing native CLI")
    if not corpus.exists():
        raise SystemExit("missing Silesia")

    out=ROOT/"exp98_parallel_decode"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    raw_total=0
    archive_total=0
    archives={}

    for name in FILES:
        src=corpus/name
        arc=out/f"{name}.kpf"
        p=subprocess.run(
            [str(cli),"c",str(src),str(arc),"1"],
            check=True,text=True,capture_output=True
        )
        m=parse_cli(p.stdout)
        assert int(m["WORKERS"])==1
        raw_total += src.stat().st_size
        archive_total += arc.stat().st_size
        archives[name]=arc

    rows=[]
    baseline=None

    for workers in WORKERS:
        file_rows=[]
        total_s=0.0

        for name in FILES:
            src=corpus/name
            src_hash=sha256(src)
            arc=archives[name]
            runs=[]

            for repeat in range(REPEATS):
                ddir=out/f"dec_{workers}_{name}_{repeat}"
                if ddir.exists():
                    shutil.rmtree(ddir)

                p=subprocess.run(
                    [str(cli),"d",str(arc),str(ddir),str(workers)],
                    check=True,text=True,capture_output=True
                )
                m=parse_cli(p.stdout)
                assert int(m["WORKERS"])==workers
                seconds=float(m["SECONDS"])
                runs.append(seconds)

                restored=ddir/name
                if not restored.is_file() or sha256(restored)!=src_hash:
                    raise SystemExit(
                        f"SHA mismatch workers={workers} file={name}"
                    )
                shutil.rmtree(ddir)

            med=statistics.median(runs)
            total_s += med
            file_rows.append({
                "file":name,
                "median_seconds":med,
                "runs_seconds":runs,
            })

        mbps=raw_total/1e6/total_s
        if baseline is None:
            baseline=mbps
        row={
            "workers":workers,
            "decode_seconds":total_s,
            "decode_MBps":mbps,
            "speedup_vs_1":mbps/baseline,
            "sha_all_pass":True,
            "per_file":file_rows,
        }
        rows.append(row)

        print(
            "EXP98_ROW",
            "WORKERS",workers,
            "DEC_S",total_s,
            "DEC_MBPS",mbps,
            "SPEEDUP",row["speedup_vs_1"],
            "SHA",True,
            flush=True,
        )

    result={
        "experiment":"EXP-98",
        "raw_bytes":raw_total,
        "archive_bytes":archive_total,
        "ratio":archive_total/raw_total,
        "repeats":REPEATS,
        "rows":rows,
    }
    Path("exp98_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert raw_total==211938580
    assert archive_total>0
    assert all(r["sha_all_pass"] for r in rows)
    print("EXP98_ARCHIVE_BYTES",archive_total,flush=True)
    print("EXP98_RATIO",archive_total/raw_total,flush=True)
    print("EXP98_SHA_ALL_PASS",flush=True)

if __name__=="__main__":
    main()
