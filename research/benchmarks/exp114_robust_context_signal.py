#!/usr/bin/env python3
"""
EXP-114 — Robust Long-Context Stability Signal

Corrects the two EXP-113 failure modes:

1. stride-sampling alias on periodic inputs;
2. selecting an 8 MiB context for inputs only slightly above 4 MiB.

Candidate policy under test:

    < 4 MiB
        -> production baseline

    4 MiB .. < 8 MiB
        robust quarter entropy spread < 0.20 -> 4 MiB / 4 MiB
        otherwise                            -> baseline

    >= 8 MiB
        robust quarter entropy spread < 0.10 -> 8 MiB / 8 MiB
        robust quarter entropy spread < 0.20 -> 4 MiB / 4 MiB
        otherwise                            -> baseline

The robust signal uses multiple contiguous windows per quarter instead of a
single strided sample.

Matrix:
- canonical Silesia;
- EXP-112 holdout regenerated deterministically;
- EXP-113 holdout regenerated deterministically;
- eight additional deterministic adversarial files.

Only three production candidates are measured: baseline, 4 MiB/4 MiB,
8 MiB/8 MiB. Every archive is decoded and SHA-256 verified.
"""
from pathlib import Path
import hashlib
import importlib.util
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
    {"label":"p4096-i4096-adaptive","parent_kib":4096,"inner_kib":4096,"force":0},
    {"label":"p8192-i8192-adaptive","parent_kib":8192,"inner_kib":8192,"force":0},
]


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def repeat_to(pattern,size):
    q,r=divmod(size,len(pattern))
    return pattern*q+pattern[:r]


def make_new_holdout(root):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    files={}

    ramp=[]
    q=3*MiB
    for width in (8,24,72,216):
        alphabet=bytes((i*17+3)&255 for i in range(width))
        ramp.append(repeat_to(alphabet,q))
    files["periodic_width_ramp"]=b"".join(ramp)

    block=random.Random(11401).randbytes(256*1024)
    files["stationary_dictionary"]=repeat_to(block,12*MiB)

    topics=[
        b"alpha beta gamma delta epsilon theta lambda stable text line\n",
        b"river forest valley mountain ocean cloud rain stable text line\n",
        b"query table index record column value database stable text line\n",
        b"parser stream archive context model engine bytes stable text line\n",
    ]
    files["four_text_topics"]=b"".join(
        repeat_to(topic,3*MiB) for topic in topics
    )

    equal=[]
    for base in (0,32,128,160):
        alphabet=bytes((base+i)&255 for i in range(96))
        equal.append(repeat_to(alphabet,3*MiB))
    files["binary_histogram_drift"]=b"".join(equal)

    files["sparse_to_dense"]=(
        b"\x00"*(3*MiB)
        + repeat_to(bytes(range(8)),3*MiB)
        + repeat_to(bytes(range(64)),3*MiB)
        + random.Random(11402).randbytes(3*MiB)
    )

    prose=b"stable context around the eight mebibyte boundary remains predictable.\n"
    files["near8m_minus"]=repeat_to(prose,8*MiB-1)
    files["near8m_plus"]=repeat_to(prose,8*MiB+1)
    files["random_stationary_16m"]=random.Random(11403).randbytes(16*MiB)

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


def read_window(path,offset,length):
    with open(path,"rb") as f:
        f.seek(offset)
        return f.read(length)


def robust_quarter_entropy(path):
    size=path.stat().st_size
    if size==0:
        return [0.0,0.0,0.0,0.0]

    window=16*1024
    windows_per_quarter=4
    result=[]

    for qi in range(4):
        start=(size*qi)//4
        end=(size*(qi+1))//4
        qlen=max(0,end-start)

        if qlen<=window*windows_per_quarter:
            data=read_window(path,start,qlen)
            result.append(entropy(data))
            continue

        max_offset=qlen-window
        pieces=[]
        for wi in range(windows_per_quarter):
            local=(max_offset*wi)//(windows_per_quarter-1)
            pieces.append(read_window(path,start+local,window))
        result.append(entropy(b"".join(pieces)))

    return result


def cheap_features(path):
    size=path.stat().st_size
    qh=robust_quarter_entropy(path)
    return {
        "raw_bytes":size,
        "quarter_entropy":qh,
        "robust_quarter_entropy_spread":max(qh)-min(qh),
    }


def choose_candidate(f):
    size=f["raw_bytes"]
    spread=f["robust_quarter_entropy_spread"]

    if size<4*MiB:
        return "baseline-adaptive"

    if size<8*MiB:
        return (
            "p4096-i4096-adaptive"
            if spread<0.20
            else "baseline-adaptive"
        )

    if spread<0.10:
        return "p8192-i8192-adaptive"
    if spread<0.20:
        return "p4096-i4096-adaptive"
    return "baseline-adaptive"


def run_config(cli,src,cfg,work,key):
    arc=work/f"{key}.{cfg['label']}.kpf"
    out=work/f"out_{key}_{cfg['label']}"

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
            f"SHA mismatch case={key} config={cfg['label']}"
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
    if len(sys.argv)!=3:
        raise SystemExit(
            "usage: exp114_robust_context_signal.py NATIVE_K75_CLI SILESIA_DIR"
        )

    cli=Path(sys.argv[1]).resolve()
    silesia=Path(sys.argv[2]).resolve()

    exp112=load_module(
        "exp112",
        ROOT/"research/benchmarks/exp112_long_context_holdout.py"
    )
    exp113=load_module(
        "exp113",
        ROOT/"research/benchmarks/exp113_long_context_holdout2.py"
    )

    datasets={}

    for p in sorted(silesia.iterdir()):
        if p.is_file():
            datasets[f"silesia/{p.name}"]=p

    for name,p in exp112.make_holdout(
        ROOT/"exp114_regression_exp112"
    ).items():
        datasets[f"exp112/{name}"]=p

    for name,p in exp113.make_holdout(
        ROOT/"exp114_regression_exp113"
    ).items():
        datasets[f"exp113/{name}"]=p

    for name,p in make_new_holdout(
        ROOT/"exp114_new_holdout"
    ).items():
        datasets[f"new/{name}"]=p

    work=ROOT/"exp114_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]
    base_total=selected_total=oracle_total=0
    regret_total=positive_regression=0
    non_regression=0
    new_holdout_positive_regression=0

    for key,src in datasets.items():
        features=cheap_features(src)
        selected_label=choose_candidate(features)

        candidates=[
            run_config(cli,src,cfg,work,key.replace("/","_"))
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
        non_regression += regression<=0
        if key.startswith("new/"):
            new_holdout_positive_regression += max(0,regression)

        rows.append({
            "case":key,
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
            "EXP114_CASE",
            "CASE",key,
            "SIZE",features["raw_bytes"],
            "SPREAD",features["robust_quarter_entropy_spread"],
            "SELECTED",selected_label,
            "ORACLE",oracle["label"],
            "REGRET",regret,
            "VS_BASE",regression,
            flush=True,
        )

    summary={
        "cases":len(rows),
        "non_regression_cases":non_regression,
        "baseline_bytes":base_total,
        "selected_bytes":selected_total,
        "oracle_bytes":oracle_total,
        "gain_vs_baseline":base_total-selected_total,
        "total_regret_bytes":regret_total,
        "positive_regression_bytes":positive_regression,
        "new_holdout_positive_regression_bytes":
            new_holdout_positive_regression,
    }

    Path("exp114_results.json").write_text(json.dumps({
        "experiment":"EXP-114",
        "policy":{
            "min_context_bytes":4*MiB,
            "max_4m_below_bytes":8*MiB,
            "spread_8m_lt":0.10,
            "spread_4m_lt":0.20,
        },
        "summary":summary,
        "rows":rows,
    },indent=2,sort_keys=True))

    print(
        "EXP114_COMPLETE",
        "CASES",summary["cases"],
        "NON_REGRESSION",summary["non_regression_cases"],
        "BASE",summary["baseline_bytes"],
        "SELECTED",summary["selected_bytes"],
        "ORACLE",summary["oracle_bytes"],
        "GAIN",summary["gain_vs_baseline"],
        "REGRET",summary["total_regret_bytes"],
        "POSITIVE_REGRESSION",summary["positive_regression_bytes"],
        "NEW_POSITIVE_REGRESSION",
            summary["new_holdout_positive_regression_bytes"],
        flush=True,
    )


if __name__=="__main__":
    main()
