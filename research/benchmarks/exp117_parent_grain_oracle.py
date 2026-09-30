#!/usr/bin/env python3
"""
EXP-117A — Parent Grain Oracle

Research-only.

Measures whether forcing a single large K75 parent grain can recover the
ratio advantage seen in EXP-110 without applying that choice globally.

For every target file we compare:
- current EXP-116 adaptive context policy;
- 4 MiB context with adaptive grain;
- 4 MiB context with forced parent grain;
- 8 MiB parent / 4 MiB inner with forced parent grain;
- 8 MiB context with adaptive grain;
- 8 MiB context with forced parent grain.

The ordinary decoder is used for all archives and every roundtrip is SHA-256
verified. Cheap EXP-116 features are recorded beside the compression results
for the next routing experiment.

Target set:
- all 12 canonical Silesia files;
- six external files > 512 KiB where parent-grain decisions are meaningful.
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

EXTERNAL=[
    ("canterbury","kennedy.xls"),
    ("calgary","book1"),
    ("calgary","book2"),
    ("large","E.coli"),
    ("large","bible.txt"),
    ("large","world192.txt"),
]

CONFIGS=[
    {"label":"adaptive","args":["adaptive"]},
    {"label":"p4-i4-adaptive","args":["4096","4096","0"]},
    {"label":"p4-i4-forced","args":["4096","4096","1"]},
    {"label":"p8-i4-forced","args":["8192","4096","1"]},
    {"label":"p8-i8-adaptive","args":["8192","8192","0"]},
    {"label":"p8-i8-forced","args":["8192","8192","1"]},
]


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


def load_feature_file():
    path=ROOT/"research"/"benchmarks"/"exp116a_structural_drift.py"
    spec=importlib.util.spec_from_file_location("exp116a",path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.feature_file


def run_config(cli,src,work,key,label,args):
    safe=key.replace("/","_")
    arc=work/f"{safe}.{label}.kpf"
    out=work/f"out_{safe}_{label}"

    cmd=[str(cli),"c",str(src),str(arc),"1",*args]
    cp=subprocess.run(cmd,check=True,text=True,capture_output=True)
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
        raise SystemExit(f"SHA mismatch file={key} config={label}")

    row={
        "archive_bytes":arc.stat().st_size,
        "archive_sha256":sha256(arc),
        "comp_seconds":float(cm["SECONDS"]),
        "dec_seconds":float(dm["SECONDS"]),
        "sha_pass":True,
    }

    shutil.rmtree(out)
    arc.unlink()
    return row


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp117_parent_grain_oracle.py NATIVE_K75_CLI")

    cli=Path(sys.argv[1]).resolve()
    work=ROOT/"exp117_parent_grain_oracle"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    feature_file=load_feature_file()

    inputs=[
        ("silesia",name,ROOT/"corpora"/"silesia"/name)
        for name in SILESIA
    ] + [
        (dataset,name,ROOT/"corpora"/dataset/name)
        for dataset,name in EXTERNAL
    ]

    rows=[]
    for dataset,name,src in inputs:
        key=f"{dataset}/{name}"
        measured={}
        for cfg in CONFIGS:
            measured[cfg["label"]]=run_config(
                cli,src,work,key,cfg["label"],cfg["args"]
            )

        oracle=min(
            measured,
            key=lambda label:measured[label]["archive_bytes"]
        )

        adaptive=measured["adaptive"]["archive_bytes"]
        forced4=measured["p4-i4-forced"]["archive_bytes"]
        adaptive4=measured["p4-i4-adaptive"]["archive_bytes"]
        forced8=measured["p8-i8-forced"]["archive_bytes"]
        adaptive8=measured["p8-i8-adaptive"]["archive_bytes"]

        row={
            "dataset":dataset,
            "file":name,
            "raw_bytes":src.stat().st_size,
            "features":feature_file(src),
            "measured":measured,
            "oracle":oracle,
            "oracle_bytes":measured[oracle]["archive_bytes"],
            "gain_oracle_vs_adaptive":
                adaptive-measured[oracle]["archive_bytes"],
            "force_gain_4m":adaptive4-forced4,
            "force_gain_8m":adaptive8-forced8,
        }
        rows.append(row)

        print(
            "EXP117_FILE",dataset,name,
            "RAW",row["raw_bytes"],
            "ADAPTIVE",adaptive,
            "ORACLE",oracle,
            "ORACLE_BYTES",row["oracle_bytes"],
            "GAIN",row["gain_oracle_vs_adaptive"],
            "FORCE4_GAIN",row["force_gain_4m"],
            "FORCE8_GAIN",row["force_gain_8m"],
            flush=True,
        )

    datasets={}
    for dataset in sorted({r["dataset"] for r in rows}):
        rs=[r for r in rows if r["dataset"]==dataset]
        raw=sum(r["raw_bytes"] for r in rs)
        adaptive=sum(r["measured"]["adaptive"]["archive_bytes"] for r in rs)
        oracle=sum(r["oracle_bytes"] for r in rs)
        fixed={
            cfg["label"]:sum(
                r["measured"][cfg["label"]]["archive_bytes"] for r in rs
            )
            for cfg in CONFIGS
        }
        datasets[dataset]={
            "raw_bytes":raw,
            "adaptive_bytes":adaptive,
            "adaptive_ratio":adaptive/raw,
            "oracle_bytes":oracle,
            "oracle_ratio":oracle/raw,
            "oracle_gain_vs_adaptive":adaptive-oracle,
            "fixed_totals":fixed,
        }
        print(
            "EXP117_DATASET",dataset,
            "RAW",raw,
            "ADAPTIVE",adaptive,
            "ADAPTIVE_RATIO",adaptive/raw,
            "ORACLE",oracle,
            "ORACLE_RATIO",oracle/raw,
            "GAIN",adaptive-oracle,
            flush=True,
        )

    s=datasets["silesia"]
    result={
        "experiment":"EXP-117A",
        "purpose":"parent-grain-oracle",
        "configs":CONFIGS,
        "datasets":datasets,
        "rows":rows,
    }
    Path("exp117_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert len(rows)==18
    assert all(
        m["sha_pass"]
        for r in rows
        for m in r["measured"].values()
    )
    assert s["raw_bytes"]==211938580
    assert s["adaptive_bytes"]==61677233
    assert s["oracle_bytes"] <= min(s["fixed_totals"].values())

    print(
        "EXP117_COMPLETE",
        "SILESIA_ADAPTIVE",s["adaptive_bytes"],
        "SILESIA_ORACLE",s["oracle_bytes"],
        "SILESIA_ORACLE_RATIO",s["oracle_ratio"],
        "SILESIA_GAIN",s["oracle_gain_vs_adaptive"],
        flush=True,
    )


if __name__=="__main__":
    main()
