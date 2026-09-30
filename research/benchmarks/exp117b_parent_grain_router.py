#!/usr/bin/env python3
"""
EXP-117B — Conservative Structural Long-Grain Router

Research-only diagnostic.

Derives a deliberately small content-only policy from the high-value Silesia
signals found by EXP-117A. It chooses between:
- current EXP-116 adaptive path;
- 8 MiB parent / 8 MiB inner context with forced parent grain.

Two interpretable gates:
A) large heterogeneous streams:
   size >= 16 MiB, quarter entropy spread >= 0.50,
   window entropy std >= 0.50.
B) medium printable streams with strong structural drift:
   4 MiB <= size < 8 MiB, printable >= 0.95,
   quarter entropy spread >= 0.50, window entropy std >= 0.20.

No file names/extensions are used.

Validation sets:
- all 12 Silesia files;
- deterministic EXP-112 holdout;
- all 32 Canterbury/Calgary/Large external files;
- new deterministic structural stress holdout designed to challenge the gates.

External/stress regressions are REPORTED, not hidden by assertions.
"""

from pathlib import Path
import hashlib
import importlib.util
import json
import random
import shutil
import subprocess
import sys

ROOT=Path.cwd()
MiB=1024*1024

SILESIA=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]

EXPECTED_SILESIA_FORCED={"mozilla","samba","reymont","xml"}

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
E116=load_module(
    "exp116",
    ROOT/"research"/"benchmarks"/"exp116a_structural_drift.py"
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

def repeat_to(data,n):
    return (data*((n+len(data)-1)//len(data)))[:n]

def make_stress(root):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    rng=random.Random(11702)
    files={}

    prose=(
        b"long range compression should distinguish repeated semantic structure "
        b"from merely heterogeneous local statistics and changing alphabets.\n"
    )
    code=(
        b"int route(int x){return (x*33)^7;}\n"
        b"struct Grain{int a;int b;int c;};\n"
    )
    markup=(
        b"<row><name>value</name><kind>test</kind><flag>true</flag></row>\n"
    )
    log=(
        b"2026-09-30 INFO worker=7 action=compress status=ok bytes=1048576\n"
    )

    # Large mixed entropy families: intended to challenge gate A.
    p=root/"s01_large_text_random.bin"
    q=6*MiB
    p.write_bytes(
        repeat_to(prose,q)+rng.randbytes(q)+
        repeat_to(code,q)+rng.randbytes(q)
    )
    files["large_text_random"]=p

    p=root/"s02_large_zero_text_random.bin"
    p.write_bytes(
        (b"\x00"*(6*MiB))+
        repeat_to(markup,6*MiB)+
        rng.randbytes(6*MiB)+
        repeat_to(log,6*MiB)
    )
    files["large_zero_text_random"]=p

    # Long-range repeated random block with local disturbances.
    block=rng.randbytes(1024*1024)
    parts=[]
    for i in range(24):
        if i in (5,11,17,23):
            parts.append(bytes([i])*MiB)
        else:
            parts.append(block)
    p=root/"s03_large_repeated_random_islands.bin"
    p.write_bytes(b"".join(parts))
    files["large_repeated_random_islands"]=p

    # Medium printable families: intended to challenge gate B.
    p=root/"s04_medium_text_families.txt"
    p.write_bytes(
        repeat_to(prose,2*MiB)+
        repeat_to(code,2*MiB)+
        repeat_to(markup,2*MiB)
    )
    files["medium_text_families"]=p

    p=root/"s05_medium_log_markup.txt"
    p.write_bytes(
        repeat_to(log,3*MiB)+
        repeat_to(markup,3*MiB)
    )
    files["medium_log_markup"]=p

    # Printable but locally volatile punctuation/alphabet mix.
    low=repeat_to(b"aaaa bbbb cccc dddd eeee\n",3*MiB)
    high=repeat_to(
        bytes(range(32,127))+b"\n",
        3*MiB
    )
    p=root/"s06_medium_printable_volatility.txt"
    p.write_bytes(low+high)
    files["medium_printable_volatility"]=p

    return files

def route(feat):
    raw=feat["raw_bytes"]
    spread=feat["quarter_entropy_spread"]
    wstd=feat["window_entropy_std"]
    printable=feat["sample_printable"]

    if (
        raw >= 16*MiB
        and spread >= 0.50
        and wstd >= 0.50
    ):
        return "p8-i8-forced", "large-heterogeneous"

    if (
        4*MiB <= raw < 8*MiB
        and printable >= 0.95
        and spread >= 0.50
        and wstd >= 0.20
    ):
        return "p8-i8-forced", "medium-printable-drift"

    return "adaptive", "default"

def measure(cli,src,work,key,label):
    safe=key.replace("/","_")
    arc=work/f"{safe}.{label}.kpf"
    out=work/f"out_{safe}_{label}"

    args=["adaptive"] if label=="adaptive" else ["8192","8192","1"]
    cp=subprocess.run(
        [str(cli),"c",str(src),str(arc),"1",*args],
        check=True,text=True,capture_output=True
    )
    cm=parse_cli(cp.stdout)

    if out.exists():
        shutil.rmtree(out)
    dp=subprocess.run(
        [str(cli),"d",str(arc),str(out),"1"],
        check=True,text=True,capture_output=True
    )
    dm=parse_cli(dp.stdout)

    restored=out/src.name
    if not restored.is_file() or sha256(restored)!=sha256(src):
        raise SystemExit(f"SHA mismatch {key} {label}")

    result={
        "archive_bytes":arc.stat().st_size,
        "comp_seconds":float(cm["SECONDS"]),
        "dec_seconds":float(dm["SECONDS"]),
        "sha_pass":True,
    }
    shutil.rmtree(out)
    arc.unlink()
    return result

def evaluate(cli,work,dataset,files):
    rows=[]
    for logical,src in files.items():
        feat=E116.feature_file(src)
        selected,reason=route(feat)

        adaptive=measure(
            cli,src,work,f"{dataset}/{logical}","adaptive"
        )
        chosen=adaptive
        forced=None
        if selected!="adaptive":
            forced=measure(
                cli,src,work,f"{dataset}/{logical}","p8-i8-forced"
            )
            chosen=forced

        delta=chosen["archive_bytes"]-adaptive["archive_bytes"]
        row={
            "file":logical,
            "features":feat,
            "selected":selected,
            "reason":reason,
            "adaptive":adaptive,
            "forced":forced,
            "chosen":chosen,
            "delta_vs_adaptive":delta,
        }
        rows.append(row)

        print(
            "EXP117B_FILE",dataset,logical,
            "SELECT",selected,
            "REASON",reason,
            "RAW",feat["raw_bytes"],
            "SPREAD",feat["quarter_entropy_spread"],
            "WSTD",feat["window_entropy_std"],
            "PRINT",feat["sample_printable"],
            "BASE",adaptive["archive_bytes"],
            "CHOSEN",chosen["archive_bytes"],
            "DELTA",delta,
            flush=True,
        )

    raw=sum(r["features"]["raw_bytes"] for r in rows)
    base=sum(r["adaptive"]["archive_bytes"] for r in rows)
    chosen=sum(r["chosen"]["archive_bytes"] for r in rows)
    base_comp=sum(r["adaptive"]["comp_seconds"] for r in rows)
    chosen_comp=sum(r["chosen"]["comp_seconds"] for r in rows)
    base_dec=sum(r["adaptive"]["dec_seconds"] for r in rows)
    chosen_dec=sum(r["chosen"]["dec_seconds"] for r in rows)

    harmful=[
        {
            "file":r["file"],
            "delta":r["delta_vs_adaptive"],
            "reason":r["reason"],
        }
        for r in rows if r["delta_vs_adaptive"]>0
    ]

    result={
        "dataset":dataset,
        "raw_bytes":raw,
        "adaptive_bytes":base,
        "chosen_bytes":chosen,
        "chosen_ratio":chosen/raw,
        "gain_vs_adaptive":base-chosen,
        "forced_count":sum(r["selected"]!="adaptive" for r in rows),
        "harmful_selections":harmful,
        "adaptive_comp_MBps":raw/1e6/base_comp,
        "chosen_comp_MBps":raw/1e6/chosen_comp,
        "adaptive_dec_MBps":raw/1e6/base_dec,
        "chosen_dec_MBps":raw/1e6/chosen_dec,
        "files":rows,
    }

    print(
        "EXP117B_DATASET",dataset,
        "RAW",raw,
        "BASE",base,
        "CHOSEN",chosen,
        "RATIO",result["chosen_ratio"],
        "GAIN",result["gain_vs_adaptive"],
        "FORCED",result["forced_count"],
        "HARM",len(harmful),
        "BASE_COMP",result["adaptive_comp_MBps"],
        "CHOSEN_COMP",result["chosen_comp_MBps"],
        flush=True,
    )
    return result

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp117b_parent_grain_router.py NATIVE_K75_CLI")

    cli=Path(sys.argv[1]).resolve()
    work=ROOT/"exp117b_parent_grain_router"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia={name:ROOT/"corpora"/"silesia"/name for name in SILESIA}

    holdout=E112.make_holdout(work/"holdout")

    external={}
    for dataset,expected in E115.DATASETS.items():
        for name in expected:
            external[f"{dataset}/{name}"]=ROOT/"corpora"/dataset/name

    stress=make_stress(work/"stress")

    datasets=[
        evaluate(cli,work,"silesia",silesia),
        evaluate(cli,work,"synthetic-holdout",holdout),
        evaluate(cli,work,"external-32",external),
        evaluate(cli,work,"structural-stress",stress),
    ]

    s=datasets[0]
    selected={
        r["file"] for r in s["files"]
        if r["selected"]!="adaptive"
    }

    result={
        "experiment":"EXP-117B",
        "purpose":"conservative-structural-long-grain-router",
        "policy":{
            "large":{
                "min_bytes":16*MiB,
                "min_spread":0.50,
                "min_window_entropy_std":0.50,
                "action":"p8-i8-forced",
            },
            "medium_printable":{
                "min_bytes":4*MiB,
                "max_bytes_exclusive":8*MiB,
                "min_printable":0.95,
                "min_spread":0.50,
                "min_window_entropy_std":0.20,
                "action":"p8-i8-forced",
            },
            "default":"adaptive",
        },
        "datasets":datasets,
    }
    Path("exp117b_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert selected==EXPECTED_SILESIA_FORCED
    assert s["adaptive_bytes"]==61677233
    assert s["chosen_bytes"]==60809713
    assert s["gain_vs_adaptive"]==867520
    assert all(
        r["chosen"]["sha_pass"]
        for d in datasets for r in d["files"]
    )

    print(
        "EXP117B_COMPLETE",
        "SILESIA",s["chosen_bytes"],
        "RATIO",s["chosen_ratio"],
        "GAIN",s["gain_vs_adaptive"],
        "EXTERNAL_HARM",len(datasets[2]["harmful_selections"]),
        "STRESS_HARM",len(datasets[3]["harmful_selections"]),
        flush=True,
    )

if __name__=="__main__":
    main()
