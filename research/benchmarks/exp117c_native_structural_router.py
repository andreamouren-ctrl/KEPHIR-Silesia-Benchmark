#!/usr/bin/env python3
"""
EXP-117C — Native Structural Router Qualification

Verifies that the native C++ adaptive policy reproduces the qualified EXP-117B
diagnostic router byte-for-byte at dataset level, while preserving ordinary
decoder compatibility and SHA-256 roundtrip integrity.

For the four selected Silesia files, native adaptive archives must also be
byte-identical to explicit p8/i8 forced archives.
"""

from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys

ROOT=Path.cwd()

SILESIA=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]
FORCED={"mozilla","samba","reymont","xml"}

EXPECTED={
    "silesia":60809713,
    "synthetic-holdout":13113511,
    "external-32":4855203,
    "structural-stress":39861207,
}

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

E112=load_module(
    "exp112",
    ROOT/"research"/"benchmarks"/"exp112_adaptive_context_router.py"
)
E115=load_module(
    "exp115",
    ROOT/"research"/"benchmarks"/"exp115_external_corpus_qualification.py"
)
E117B=load_module(
    "exp117b",
    ROOT/"research"/"benchmarks"/"exp117b_parent_grain_router.py"
)

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

def compress(cli,src,arc,args):
    cp=subprocess.run(
        [str(cli),"c",str(src),str(arc),"1",*args],
        check=True,text=True,capture_output=True
    )
    return parse_cli(cp.stdout)

def verify_decode(cli,src,arc,out):
    if out.exists():
        shutil.rmtree(out)
    dp=subprocess.run(
        [str(cli),"d",str(arc),str(out),"1"],
        check=True,text=True,capture_output=True
    )
    dm=parse_cli(dp.stdout)
    restored=out/src.name
    ok=restored.is_file() and sha256(restored)==sha256(src)
    shutil.rmtree(out)
    if not ok:
        raise SystemExit(f"SHA mismatch {src}")
    return dm

def evaluate(cli,work,dataset,files):
    rows=[]
    for name,src in files.items():
        safe=(dataset+"_"+name).replace("/","_")
        arc=work/f"{safe}.adaptive.kpf"
        out=work/f"out_{safe}"

        cm=compress(cli,src,arc,["adaptive"])
        dm=verify_decode(cli,src,arc,out)

        row={
            "file":name,
            "raw_bytes":src.stat().st_size,
            "archive_bytes":arc.stat().st_size,
            "archive_sha256":sha256(arc),
            "comp_seconds":float(cm["SECONDS"]),
            "dec_seconds":float(dm["SECONDS"]),
            "sha_pass":True,
        }

        if dataset=="silesia" and name in FORCED:
            forced=work/f"{safe}.forced.kpf"
            compress(cli,src,forced,["8192","8192","1"])
            row["forced_archive_bytes"]=forced.stat().st_size
            row["forced_archive_sha256"]=sha256(forced)
            row["matches_explicit_forced"]=(
                row["archive_sha256"]==row["forced_archive_sha256"]
            )
            if not row["matches_explicit_forced"]:
                raise SystemExit(
                    f"native adaptive != explicit forced for {name}"
                )
            forced.unlink()

        rows.append(row)
        arc.unlink()

        print(
            "EXP117C_FILE",dataset,name,
            "RAW",row["raw_bytes"],
            "BYTES",row["archive_bytes"],
            "FORCED_MATCH",row.get("matches_explicit_forced","NA"),
            flush=True,
        )

    raw=sum(r["raw_bytes"] for r in rows)
    total=sum(r["archive_bytes"] for r in rows)
    comp=sum(r["comp_seconds"] for r in rows)
    dec=sum(r["dec_seconds"] for r in rows)

    result={
        "dataset":dataset,
        "raw_bytes":raw,
        "archive_bytes":total,
        "ratio":total/raw,
        "comp_MBps":raw/1e6/comp,
        "dec_MBps":raw/1e6/dec,
        "files":rows,
    }

    print(
        "EXP117C_DATASET",dataset,
        "RAW",raw,
        "BYTES",total,
        "RATIO",result["ratio"],
        "COMP_MBPS",result["comp_MBps"],
        "DEC_MBPS",result["dec_MBps"],
        flush=True,
    )
    return result

def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp117c_native_structural_router.py NATIVE_K75_CLI"
        )

    cli=Path(sys.argv[1]).resolve()
    work=ROOT/"exp117c_native_router"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia={n:ROOT/"corpora"/"silesia"/n for n in SILESIA}
    synthetic=E112.make_holdout(work/"synthetic")
    external={
        f"{dataset}/{name}":ROOT/"corpora"/dataset/name
        for dataset,files in E115.DATASETS.items()
        for name in files
    }
    stress=E117B.make_stress(work/"stress")

    datasets=[
        evaluate(cli,work,"silesia",silesia),
        evaluate(cli,work,"synthetic-holdout",synthetic),
        evaluate(cli,work,"external-32",external),
        evaluate(cli,work,"structural-stress",stress),
    ]

    for d in datasets:
        assert d["archive_bytes"]==EXPECTED[d["dataset"]]

    assert all(
        r["sha_pass"]
        for d in datasets
        for r in d["files"]
    )

    s=datasets[0]
    assert all(
        r.get("matches_explicit_forced",True)
        for r in s["files"]
    )

    result={
        "experiment":"EXP-117C",
        "purpose":"native-structural-router-qualification",
        "expected_bytes":EXPECTED,
        "datasets":datasets,
    }
    Path("exp117c_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print(
        "EXP117C_VALIDATION_PASS",
        "SILESIA",s["archive_bytes"],
        "RATIO",s["ratio"],
        "COMP_MBPS",s["comp_MBps"],
        "DEC_MBPS",s["dec_MBps"],
        flush=True,
    )

if __name__=="__main__":
    main()
