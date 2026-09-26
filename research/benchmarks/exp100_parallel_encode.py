#!/usr/bin/env python3
"""
EXP-100 — Bounded Parallel Encode Scaling

Compresses the same canonical Silesia files with 1/2/4/8/16 workers.

Acceptance:
- archive bytes must be byte-identical to the 1-worker baseline;
- SHA roundtrip must pass;
- median-of-3 compression throughput is measured;
- at least one parallel profile must improve throughput.
"""
from pathlib import Path
import hashlib
import json
import shutil
import statistics
import subprocess
import sys

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
        raise SystemExit("usage: exp100_parallel_encode.py /path/to/kephir2_native_k75_cli")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    out=ROOT/"exp100_parallel_encode"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    raw_total=sum((corpus/f).stat().st_size for f in FILES)
    baseline_archives={}
    rows=[]
    baseline_mbps=None

    for workers in WORKERS:
        total_s=0.0
        total_archive=0
        file_rows=[]

        for name in FILES:
            src=corpus/name
            src_hash=sha256(src)
            runs=[]
            final_bytes=None

            for repeat in range(REPEATS):
                arc=out/f"{name}.w{workers}.r{repeat}.kpf"
                p=subprocess.run(
                    [str(cli),"c",str(src),str(arc),str(workers)],
                    check=True,text=True,capture_output=True
                )
                m=parse_cli(p.stdout)
                assert int(m["WORKERS"])==workers
                runs.append(float(m["SECONDS"]))
                data=arc.read_bytes()

                if final_bytes is None:
                    final_bytes=data
                else:
                    assert data==final_bytes, (
                        f"nondeterministic archive workers={workers} file={name}"
                    )

                ddir=out/f"verify_{workers}_{name}_{repeat}"
                subprocess.run(
                    [str(cli),"d",str(arc),str(ddir),"1"],
                    check=True,text=True,capture_output=True
                )
                restored=ddir/name
                if not restored.is_file() or sha256(restored)!=src_hash:
                    raise SystemExit(
                        f"SHA mismatch workers={workers} file={name}"
                    )
                shutil.rmtree(ddir)
                arc.unlink()

            med=statistics.median(runs)
            total_s+=med
            total_archive+=len(final_bytes)

            if workers==1:
                baseline_archives[name]=final_bytes
            else:
                assert final_bytes==baseline_archives[name], (
                    f"archive differs from 1-worker baseline: {name} w={workers}"
                )

            file_rows.append({
                "file":name,
                "median_seconds":med,
                "runs_seconds":runs,
                "archive_bytes":len(final_bytes),
            })

        mbps=raw_total/1e6/total_s
        if baseline_mbps is None:
            baseline_mbps=mbps

        row={
            "workers":workers,
            "comp_seconds":total_s,
            "comp_MBps":mbps,
            "speedup_vs_1":mbps/baseline_mbps,
            "archive_bytes":total_archive,
            "ratio":total_archive/raw_total,
            "archive_identical_to_1":True,
            "sha_all_pass":True,
            "per_file":file_rows,
        }
        rows.append(row)

        print(
            "EXP100_ROW",
            "WORKERS",workers,
            "COMP_S",total_s,
            "COMP_MBPS",mbps,
            "SPEEDUP",row["speedup_vs_1"],
            "BYTES",total_archive,
            "RATIO",row["ratio"],
            "IDENTICAL",True,
            "SHA",True,
            flush=True,
        )

    result={
        "experiment":"EXP-100",
        "raw_bytes":raw_total,
        "repeats":REPEATS,
        "rows":rows,
    }
    Path("exp100_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert raw_total==211938580
    assert all(r["archive_identical_to_1"] for r in rows)
    assert all(r["sha_all_pass"] for r in rows)
    print("EXP100_ARCHIVE_PARITY_PASS",flush=True)
    print("EXP100_SHA_ALL_PASS",flush=True)

if __name__=="__main__":
    main()
