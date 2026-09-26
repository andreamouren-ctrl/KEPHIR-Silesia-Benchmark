#!/usr/bin/env python3
"""
EXP-91 — Native Backend Gap Qualification

Compares the current qualified Python KEPHIR 1.0.0-rc1 single-file path with
the first fully in-process C++ NativeK75 candidate on the canonical Silesia
files.

This is intentionally an application-replacement gap test, not an algorithm
claim. Both paths emit full KPF1 single-file archives and both outputs are
decoded and SHA-verified.

Metrics:
- full archive bytes / ratio
- compression time
- decompression time
- per-file and aggregate deltas
- lossless roundtrip
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K

FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml"
]


def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def fresh_model():
    return K.merge_models(K.load_factory(True),{})


def parse_cli(text):
    out={}
    for line in text.splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            out[k.strip()]=v.strip()
    return out


def run_native(cli,src,work,label):
    arc=work/f"{label}.native.kpf"
    out=work/f"{label}_native_out"

    cp=subprocess.run(
        [str(cli),"c",str(src),str(arc)],
        check=True,text=True,capture_output=True
    )
    cm=parse_cli(cp.stdout)

    if out.exists():
        shutil.rmtree(out)
    dp=subprocess.run(
        [str(cli),"d",str(arc),str(out)],
        check=True,text=True,capture_output=True
    )
    dm=parse_cli(dp.stdout)

    restored=out/src.name
    ok=restored.is_file() and sha256(restored)==sha256(src)
    if not ok:
        raise SystemExit("native SHA failure: "+label)

    return {
        "archive_bytes":arc.stat().st_size,
        "comp_time_s":float(cm["SECONDS"]),
        "dec_time_s":float(dm["SECONDS"]),
        "sha_ok":ok,
    }


def run_python(src,work,label,model):
    arc=work/f"{label}.python.kpf"
    out=work/f"{label}_python_out"
    tmp=work/f"{label}.python.tmp"

    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    t0=time.perf_counter()
    stats=K.compress_file(src,arc,model,tmp/"enc")
    comp=time.perf_counter()-t0

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    t0=time.perf_counter()
    written=K.extract_archive(arc,out,tmp/"dec")
    dec=time.perf_counter()-t0

    restored=out/src.name
    ok=restored.is_file() and sha256(restored)==sha256(src)
    if not ok:
        raise SystemExit("python SHA failure: "+label)

    return {
        "archive_bytes":arc.stat().st_size,
        "comp_time_s":comp,
        "dec_time_s":dec,
        "sha_ok":ok,
        "stats":stats,
        "written":[str(p) for p in written],
    }


def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp91_native_backend_gap.py /path/to/kephir2_native_k75_cli"
        )

    cli=Path(sys.argv[1]).resolve()
    if not cli.exists():
        raise SystemExit("native K75 CLI missing: "+str(cli))

    corpus=ROOT/"corpora"/"silesia"
    if not corpus.exists():
        raise SystemExit("canonical Silesia missing")

    outdir=ROOT/"exp91_backend_gap"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir()

    model=fresh_model()
    rows=[]

    for name in FILES:
        src=corpus/name
        if not src.is_file():
            raise SystemExit("missing Silesia file: "+name)

        raw=src.stat().st_size
        print("EXP91_BEGIN",name,"RAW",raw,flush=True)

        py=run_python(src,outdir,name,model)
        native=run_native(cli,src,outdir,name)

        row={
            "file":name,
            "raw_bytes":raw,
            "python":py,
            "native":native,
            "native_minus_python_bytes":
                native["archive_bytes"]-py["archive_bytes"],
            "native_over_python_size":
                native["archive_bytes"]/py["archive_bytes"]
                if py["archive_bytes"] else 0.0,
        }
        rows.append(row)

        print(
            "EXP91_FILE",name,
            "PY_BYTES",py["archive_bytes"],
            "NATIVE_BYTES",native["archive_bytes"],
            "DELTA",row["native_minus_python_bytes"],
            "PY_COMP_S",py["comp_time_s"],
            "NATIVE_COMP_S",native["comp_time_s"],
            "PY_DEC_S",py["dec_time_s"],
            "NATIVE_DEC_S",native["dec_time_s"],
            "SHA",py["sha_ok"] and native["sha_ok"],
            flush=True,
        )

    raw=sum(r["raw_bytes"] for r in rows)
    py_bytes=sum(r["python"]["archive_bytes"] for r in rows)
    native_bytes=sum(r["native"]["archive_bytes"] for r in rows)
    py_comp=sum(r["python"]["comp_time_s"] for r in rows)
    native_comp=sum(r["native"]["comp_time_s"] for r in rows)
    py_dec=sum(r["python"]["dec_time_s"] for r in rows)
    native_dec=sum(r["native"]["dec_time_s"] for r in rows)

    aggregate={
        "raw_bytes":raw,
        "python_archive_bytes":py_bytes,
        "native_archive_bytes":native_bytes,
        "python_ratio":py_bytes/raw,
        "native_ratio":native_bytes/raw,
        "native_minus_python_bytes":native_bytes-py_bytes,
        "native_over_python_size":native_bytes/py_bytes,
        "python_comp_time_s":py_comp,
        "native_comp_time_s":native_comp,
        "python_dec_time_s":py_dec,
        "native_dec_time_s":native_dec,
        "python_comp_MBps":raw/1e6/py_comp if py_comp else 0.0,
        "native_comp_MBps":raw/1e6/native_comp if native_comp else 0.0,
        "python_dec_MBps":raw/1e6/py_dec if py_dec else 0.0,
        "native_dec_MBps":raw/1e6/native_dec if native_dec else 0.0,
        "sha_all_pass":all(
            r["python"]["sha_ok"] and r["native"]["sha_ok"]
            for r in rows
        ),
    }

    result={
        "experiment":"EXP-91",
        "purpose":"native-backend-gap-qualification",
        "python_version":K.VERSION,
        "rows":rows,
        "aggregate":aggregate,
    }

    Path("exp91_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP91_AGGREGATE",json.dumps(aggregate,sort_keys=True),flush=True)
    if not aggregate["sha_all_pass"]:
        raise SystemExit("EXP91 SHA failure")
    print("EXP91_SHA_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
