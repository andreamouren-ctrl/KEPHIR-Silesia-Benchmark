#!/usr/bin/env python3
"""
EXP-115 — External Corpus Qualification

Research-only.

Qualifies the EXP-114 native adaptive-context router on three external,
well-known lossless-compression corpora that were not used to derive the
policy:
- Canterbury Corpus
- Calgary Corpus
- Canterbury Large Corpus

For every file measure:
- production baseline
- explicit 4 MiB context
- explicit 8 MiB context
- native adaptive context

Every archive is decoded with the ordinary decoder and SHA-256 verified.
The experiment reports harmful adaptive selections but does not hide/fail on
them: its purpose is independent validation before production promotion.
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path.cwd()

DATASETS={
    "canterbury":{
        "alice29.txt":152089,
        "asyoulik.txt":125179,
        "cp.html":24603,
        "fields.c":11150,
        "grammar.lsp":3721,
        "kennedy.xls":1029744,
        "lcet10.txt":426754,
        "plrabn12.txt":481861,
        "ptt5":513216,
        "sum":38240,
        "xargs.1":4227,
    },
    "calgary":{
        "bib":111261,
        "book1":768771,
        "book2":610856,
        "geo":102400,
        "news":377109,
        "obj1":21504,
        "obj2":246814,
        "paper1":53161,
        "paper2":82199,
        "pic":513216,
        "progc":39611,
        "progl":71646,
        "progp":49379,
        "trans":93695,
    },
    "large":{
        "E.coli":4638690,
        "bible.txt":4047392,
        "world192.txt":2473400,
    },
}

CONFIGS={
    "baseline":[],
    "ctx4m":["4096","4096","0"],
    "ctx8m":["8192","8192","0"],
    "adaptive":["adaptive"],
}
REFS=("baseline","ctx4m","ctx8m")


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


def validate_corpus(root,expected):
    actual={
        p.name:p.stat().st_size
        for p in root.iterdir()
        if p.is_file()
    }
    if actual != expected:
        missing=sorted(set(expected)-set(actual))
        extra=sorted(set(actual)-set(expected))
        wrong={
            k:(expected[k],actual[k])
            for k in expected.keys() & actual.keys()
            if expected[k] != actual[k]
        }
        raise SystemExit(
            f"corpus mismatch root={root} missing={missing} "
            f"extra={extra} wrong={wrong}"
        )


def run_one(cli,src,work,dataset,label):
    arc=work/f"{dataset}_{src.name}_{label}.kpf"
    out=work/f"out_{dataset}_{src.name}_{label}"
    cmd=[str(cli),"c",str(src),str(arc),"1"]+CONFIGS[label]

    cp=subprocess.run(
        cmd,check=True,text=True,capture_output=True
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
        raise SystemExit(
            f"SHA mismatch {dataset}/{src.name} cfg={label}"
        )

    result={
        "archive_bytes":arc.stat().st_size,
        "archive_sha256":sha256(arc),
        "comp_seconds":float(cm["SECONDS"]),
        "dec_seconds":float(dm["SECONDS"]),
        "sha_pass":True,
    }

    shutil.rmtree(out)
    arc.unlink()
    return result


def evaluate(cli,work,dataset,root,expected):
    validate_corpus(root,expected)
    rows=[]

    for name,size in expected.items():
        src=root/name
        measured={
            label:run_one(cli,src,work,dataset,label)
            for label in (*REFS,"adaptive")
        }

        oracle=min(
            REFS,
            key=lambda label:(
                measured[label]["archive_bytes"],
                REFS.index(label),
            )
        )

        ah=measured["adaptive"]["archive_sha256"]
        matches=[
            label for label in REFS
            if measured[label]["archive_sha256"]==ah
        ]

        delta=(
            measured["adaptive"]["archive_bytes"]
            - measured["baseline"]["archive_bytes"]
        )
        regret=(
            measured["adaptive"]["archive_bytes"]
            - measured[oracle]["archive_bytes"]
        )

        row={
            "file":name,
            "raw_bytes":size,
            "oracle":oracle,
            "adaptive_matches":matches,
            "adaptive_delta_vs_baseline":delta,
            "adaptive_regret":regret,
            "measured":measured,
        }
        rows.append(row)

        print(
            "EXP115_FILE",dataset,name,
            "RAW",size,
            "ORACLE",oracle,
            "MATCH",",".join(matches) if matches else "NONE",
            "DELTA_BASE",delta,
            "REGRET",regret,
            flush=True,
        )

    raw_total=sum(r["raw_bytes"] for r in rows)
    baseline=sum(r["measured"]["baseline"]["archive_bytes"] for r in rows)
    adaptive=sum(r["measured"]["adaptive"]["archive_bytes"] for r in rows)
    oracle=sum(r["measured"][r["oracle"]]["archive_bytes"] for r in rows)
    comp=sum(r["measured"]["adaptive"]["comp_seconds"] for r in rows)
    dec=sum(r["measured"]["adaptive"]["dec_seconds"] for r in rows)

    harmful=[
        {
            "file":r["file"],
            "delta_vs_baseline":r["adaptive_delta_vs_baseline"],
            "regret":r["adaptive_regret"],
            "oracle":r["oracle"],
            "adaptive_matches":r["adaptive_matches"],
        }
        for r in rows
        if r["adaptive_delta_vs_baseline"]>0
    ]

    result={
        "dataset":dataset,
        "file_count":len(rows),
        "raw_bytes":raw_total,
        "baseline_bytes":baseline,
        "adaptive_bytes":adaptive,
        "adaptive_ratio":adaptive/raw_total,
        "oracle_bytes":oracle,
        "gain_vs_baseline":baseline-adaptive,
        "regret_vs_oracle":adaptive-oracle,
        "harmful_selections":harmful,
        "adaptive_comp_MBps":raw_total/1e6/comp,
        "adaptive_dec_MBps":raw_total/1e6/dec,
        "files":rows,
    }

    print(
        "EXP115_DATASET",dataset,
        "RAW",raw_total,
        "BASE",baseline,
        "ADAPTIVE",adaptive,
        "RATIO",result["adaptive_ratio"],
        "ORACLE",oracle,
        "GAIN",result["gain_vs_baseline"],
        "REGRET",result["regret_vs_oracle"],
        "HARM",len(harmful),
        "COMP_MBPS",result["adaptive_comp_MBps"],
        "DEC_MBPS",result["adaptive_dec_MBps"],
        flush=True,
    )
    return result


def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp115_external_corpus_qualification.py NATIVE_K75_CLI"
        )

    cli=Path(sys.argv[1]).resolve()
    corpora=ROOT/"corpora"
    work=ROOT/"exp115_external_corpus"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    datasets=[
        evaluate(cli,work,name,corpora/name,expected)
        for name,expected in DATASETS.items()
    ]

    raw_total=sum(d["raw_bytes"] for d in datasets)
    baseline=sum(d["baseline_bytes"] for d in datasets)
    adaptive=sum(d["adaptive_bytes"] for d in datasets)
    oracle=sum(d["oracle_bytes"] for d in datasets)
    harmful=[
        {"dataset":d["dataset"],**h}
        for d in datasets
        for h in d["harmful_selections"]
    ]

    result={
        "experiment":"EXP-115",
        "purpose":"external-corpus-qualification",
        "datasets":datasets,
        "aggregate":{
            "raw_bytes":raw_total,
            "baseline_bytes":baseline,
            "adaptive_bytes":adaptive,
            "adaptive_ratio":adaptive/raw_total,
            "oracle_bytes":oracle,
            "gain_vs_baseline":baseline-adaptive,
            "regret_vs_oracle":adaptive-oracle,
            "harmful_selections":harmful,
        },
    }

    Path("exp115_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert raw_total==17111888
    assert sum(d["file_count"] for d in datasets)==28
    assert all(
        m["sha_pass"]
        for d in datasets
        for row in d["files"]
        for m in row["measured"].values()
    )

    a=result["aggregate"]
    print(
        "EXP115_COMPLETE",
        "RAW",a["raw_bytes"],
        "BASE",a["baseline_bytes"],
        "ADAPTIVE",a["adaptive_bytes"],
        "RATIO",a["adaptive_ratio"],
        "ORACLE",a["oracle_bytes"],
        "GAIN",a["gain_vs_baseline"],
        "REGRET",a["regret_vs_oracle"],
        "HARM",len(a["harmful_selections"]),
        flush=True,
    )


if __name__=="__main__":
    main()
