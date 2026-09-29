#!/usr/bin/env python3
"""
EXP-113 — Second Unseen Long-Context Holdout

Frozen candidate from EXP-112:

    size >= 4 MiB and spread < 0.10 -> 8 MiB parent / 8 MiB inner
    size >= 4 MiB and spread < 0.20 -> 4 MiB parent / 4 MiB inner
    otherwise                       -> production baseline

The workloads below are new and were not used to derive the thresholds.
No production code is changed.
"""
from pathlib import Path
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys

ROOT=Path.cwd()
MiB=1024*1024

CONFIGS=[
    {"label":"baseline-adaptive","parent_kib":0,"inner_kib":0,"force":0},
    {"label":"p4096-i512-adaptive","parent_kib":4096,"inner_kib":512,"force":0},
    {"label":"p4096-i1024-adaptive","parent_kib":4096,"inner_kib":1024,"force":0},
    {"label":"p4096-i2048-adaptive","parent_kib":4096,"inner_kib":2048,"force":0},
    {"label":"p4096-i4096-adaptive","parent_kib":4096,"inner_kib":4096,"force":0},
    {"label":"p8192-i512-adaptive","parent_kib":8192,"inner_kib":512,"force":0},
    {"label":"p8192-i4096-adaptive","parent_kib":8192,"inner_kib":4096,"force":0},
    {"label":"p8192-i8192-adaptive","parent_kib":8192,"inner_kib":8192,"force":0},
]


def repeat_to(pattern,size):
    q,r=divmod(size,len(pattern))
    return pattern*q+pattern[:r]


def make_holdout(root):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    json_line=(
        b'{"id":123456,"state":"active","region":"eu","score":42,'
        b'"message":"stable event payload"}\n'
    )
    csv_line=b"123456,2026-09-29,active,eu,42.125,stable-record\n"
    utf16=("The long document carries stable repeated language and context.\n"
           .encode("utf-16le"))
    sparse=(b"\x00"*240)+bytes(range(16))
    code=(
        b"\x55\x48\x89\xe5\x48\x83\xec\x20\x48\x8b\x45\xf8"
        b"\x48\x01\xd0\x5d\xc3"
    )

    files={}
    files["json_log"]=repeat_to(json_line,10*MiB)
    files["csv_numeric"]=repeat_to(csv_line,10*MiB)
    files["utf16le_text"]=repeat_to(utf16,10*MiB)
    files["sparse_binary"]=repeat_to(sparse,10*MiB)
    files["machine_code_like"]=repeat_to(code,10*MiB)

    block1=random.Random(11301).randbytes(1*MiB)
    block4=random.Random(11302).randbytes(4*MiB)
    files["repeated_1m_random"]=repeat_to(block1,12*MiB)
    files["repeated_4m_random"]=repeat_to(block4,12*MiB)
    files["random_stationary_12m"]=random.Random(11303).randbytes(12*MiB)

    q=3*MiB
    regimes=[]
    for base in (0,64,128,192):
        alphabet=bytes((base+i)&255 for i in range(64))
        regimes.append(repeat_to(alphabet,q))
    files["regime_equal_entropy"]=b"".join(regimes)

    local=[]
    for seed in (11310,11311,11312,11313):
        block=random.Random(seed).randbytes(64*1024)
        local.append(repeat_to(block,q))
    files["local_model_shift"]=b"".join(local)

    gradual=[]
    for width in (16,32,64,128):
        gradual.append(repeat_to(bytes(range(width)),q))
    files["gradual_alphabet"]=b"".join(gradual)

    files["mixed_text_zero_random"]=(
        repeat_to(json_line,q)
        + b"\x00"*q
        + random.Random(11320).randbytes(q)
        + repeat_to(code,q)
    )

    files["periodic_257"]=repeat_to(
        bytes((i*37+11)&255 for i in range(257)),
        10*MiB
    )

    prose=repeat_to(
        b"stable prose phrase repeated through the block for context.\n",
        1*MiB
    )
    alt=[]
    for i in range(12):
        alt.append(
            prose if i%2==0
            else random.Random(11400+i).randbytes(1*MiB)
        )
    files["alternating_1m"]=b"".join(alt)

    files["just_below_4m"]=repeat_to(json_line,4*MiB-1)
    files["just_above_4m"]=repeat_to(json_line,4*MiB+1)

    out={}
    for name,data in files.items():
        p=root/f"{name}.dat"
        p.write_bytes(data)
        out[name]=p
    return out


def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(MiB),b""):
            h.update(block)
    return h.hexdigest()


def parse_cli(text):
    out={}
    for line in text.splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            out[k.strip()]=v.strip()
    return out


def entropy(data):
    if not data:
        return 0.0
    counts=[0]*256
    for b in data:
        counts[b]+=1
    n=len(data)
    h=0.0
    for count in counts:
        if count:
            p=count/n
            h-=p*math.log2(p)
    return h


def stride_sample(data,target=8192):
    if not data:
        return b""
    step=max(1,len(data)//target)
    return data[::step]


def cheap_features(path):
    data=path.read_bytes()
    sample=stride_sample(data)
    n=max(1,len(sample))
    printable=sum(
        1 for b in sample
        if b in (9,10,13) or 32<=b<127
    )/n
    zeros=sample.count(0)/n

    q=max(1,len(data)//4)
    hs=[]
    for i in range(4):
        start=i*q
        end=len(data) if i==3 else min(len(data),(i+1)*q)
        hs.append(entropy(stride_sample(data[start:end],4096)))

    return {
        "raw_bytes":len(data),
        "sample_entropy":entropy(sample),
        "sample_printable_fraction":printable,
        "sample_zero_fraction":zeros,
        "quarter_entropy_spread":max(hs)-min(hs),
    }


def choose_candidate(f):
    if f["raw_bytes"]<4*MiB:
        return "baseline-adaptive"
    spread=f["quarter_entropy_spread"]
    if spread<0.10:
        return "p8192-i8192-adaptive"
    if spread<0.20:
        return "p4096-i4096-adaptive"
    return "baseline-adaptive"


def run_config(cli,src,cfg,work,name):
    arc=work/f"{name}.{cfg['label']}.kpf"
    out=work/f"out_{name}_{cfg['label']}"

    cmd=[str(cli),"c",str(src),str(arc),"1"]
    if cfg["parent_kib"]:
        cmd += [
            str(cfg["parent_kib"]),
            str(cfg["inner_kib"]),
            str(cfg["force"]),
        ]

    cp=subprocess.run(cmd,check=True,text=True,capture_output=True)
    cm=parse_cli(cp.stdout)

    dp=subprocess.run(
        [str(cli),"d",str(arc),str(out),"1"],
        check=True,text=True,capture_output=True
    )
    dm=parse_cli(dp.stdout)

    restored=out/src.name
    if not restored.is_file() or sha256(restored)!=sha256(src):
        raise SystemExit(
            f"SHA mismatch holdout={name} config={cfg['label']}"
        )

    result={
        "label":cfg["label"],
        "archive_bytes":arc.stat().st_size,
        "comp_seconds":float(cm["SECONDS"]),
        "dec_seconds":float(dm["SECONDS"]),
        "sha":True,
    }

    shutil.rmtree(out)
    arc.unlink()
    return result


def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp113_long_context_holdout2.py NATIVE_K75_CLI"
        )

    cli=Path(sys.argv[1]).resolve()
    inputs=make_holdout(ROOT/"exp113_holdout_inputs")
    work=ROOT/"exp113_holdout_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]
    base_total=selected_total=oracle_total=0
    regret_total=positive_regression=0
    zero_regression_cases=0

    for name,src in inputs.items():
        features=cheap_features(src)
        selected_label=choose_candidate(features)

        candidates=[
            run_config(cli,src,cfg,work,name)
            for cfg in CONFIGS
        ]
        by_label={x["label"]:x for x in candidates}
        base=by_label["baseline-adaptive"]
        selected=by_label[selected_label]
        oracle=min(candidates,key=lambda x:x["archive_bytes"])

        regret=selected["archive_bytes"]-oracle["archive_bytes"]
        regression=selected["archive_bytes"]-base["archive_bytes"]

        base_total+=base["archive_bytes"]
        selected_total+=selected["archive_bytes"]
        oracle_total+=oracle["archive_bytes"]
        regret_total+=regret
        positive_regression+=max(0,regression)
        zero_regression_cases += regression<=0

        rows.append({
            "name":name,
            "features":features,
            "selected":selected_label,
            "oracle":oracle["label"],
            "baseline_bytes":base["archive_bytes"],
            "selected_bytes":selected["archive_bytes"],
            "oracle_bytes":oracle["archive_bytes"],
            "regret_bytes":regret,
            "regression_vs_baseline":regression,
            "candidates":candidates,
        })

        print(
            "EXP113_CASE",
            "NAME",name,
            "SPREAD",features["quarter_entropy_spread"],
            "SELECTED",selected_label,
            "ORACLE",oracle["label"],
            "REGRET",regret,
            "VS_BASE",regression,
            flush=True,
        )

    summary={
        "cases":len(rows),
        "non_regression_cases":zero_regression_cases,
        "baseline_bytes":base_total,
        "selected_bytes":selected_total,
        "oracle_bytes":oracle_total,
        "gain_vs_baseline":base_total-selected_total,
        "total_regret_bytes":regret_total,
        "positive_regression_bytes":positive_regression,
    }

    Path("exp113_results.json").write_text(json.dumps({
        "experiment":"EXP-113",
        "frozen_gate":{
            "min_bytes":4*MiB,
            "spread_lt_8m":0.10,
            "spread_lt_4m":0.20,
            "choice_8m":"p8192-i8192-adaptive",
            "choice_4m":"p4096-i4096-adaptive",
            "fallback":"baseline-adaptive",
        },
        "summary":summary,
        "rows":rows,
    },indent=2,sort_keys=True))

    print(
        "EXP113_COMPLETE",
        "CASES",summary["cases"],
        "NON_REGRESSION",summary["non_regression_cases"],
        "BASE",summary["baseline_bytes"],
        "SELECTED",summary["selected_bytes"],
        "ORACLE",summary["oracle_bytes"],
        "GAIN",summary["gain_vs_baseline"],
        "REGRET",summary["total_regret_bytes"],
        "POSITIVE_REGRESSION",summary["positive_regression_bytes"],
        flush=True,
    )


if __name__=="__main__":
    main()
