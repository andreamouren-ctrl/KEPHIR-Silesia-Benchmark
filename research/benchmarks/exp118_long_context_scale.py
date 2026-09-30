#!/usr/bin/env python3
"""
EXP-118A — Long Context Scale Decomposition

Research-only.

Tests whether K75 gains new useful redundancy beyond the current 8 MiB
research ceiling. The first pass is intentionally limited to the four large
Silesia streams that dominate compressed size:
mozilla, nci, samba, webster.

Configurations separate parent span from AUR2 inner chunk scale:
- current native adaptive policy
- p8/i8 forced reference
- p16/i8 forced   (parent-only scale)
- p16/i16 forced
- p32/i16 forced (parent-only scale above 16)
- p32/i32 forced

Every archive is decoded by the ordinary decoder and SHA-256 verified.
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path.cwd()
FILES=["mozilla","nci","samba","webster"]

CONFIGS=[
    ("adaptive",["adaptive"]),
    ("p8-i8-forced",["8192","8192","1"]),
    ("p16-i8-forced",["16384","8192","1"]),
    ("p16-i16-forced",["16384","16384","1"]),
    ("p32-i16-forced",["32768","16384","1"]),
    ("p32-i32-forced",["32768","32768","1"]),
]

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def parse(text):
    out={}
    for line in text.splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            out[k.strip()]=v.strip()
    return out

def run(cli,src,work,label,args):
    arc=work/f"{src.name}.{label}.kpf"
    out=work/f"out_{src.name}_{label}"

    cp=subprocess.run(
        [str(cli),"c",str(src),str(arc),"1",*args],
        check=True,text=True,capture_output=True
    )
    cm=parse(cp.stdout)

    if out.exists():
        shutil.rmtree(out)
    dp=subprocess.run(
        [str(cli),"d",str(arc),str(out),"1"],
        check=True,text=True,capture_output=True
    )
    dm=parse(dp.stdout)

    restored=out/src.name
    if not restored.is_file() or sha256(restored)!=sha256(src):
        raise SystemExit(f"SHA mismatch {src.name} {label}")

    result={
        "archive_bytes":arc.stat().st_size,
        "comp_seconds":float(cm["SECONDS"]),
        "dec_seconds":float(dm["SECONDS"]),
        "sha_pass":True,
    }
    shutil.rmtree(out)
    arc.unlink()
    return result

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp118_long_context_scale.py NATIVE_K75_CLI")

    cli=Path(sys.argv[1]).resolve()
    work=ROOT/"exp118_long_context_scale"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]
    for name in FILES:
        src=ROOT/"corpora"/"silesia"/name
        measured={}
        for label,args in CONFIGS:
            measured[label]=run(cli,src,work,label,args)

        oracle=min(
            measured,
            key=lambda x:measured[x]["archive_bytes"]
        )
        base=measured["adaptive"]["archive_bytes"]
        row={
            "file":name,
            "raw_bytes":src.stat().st_size,
            "measured":measured,
            "oracle":oracle,
            "oracle_bytes":measured[oracle]["archive_bytes"],
            "gain_vs_adaptive":base-measured[oracle]["archive_bytes"],
        }
        rows.append(row)

        print(
            "EXP118_FILE",name,
            "RAW",row["raw_bytes"],
            "ADAPTIVE",base,
            "ORACLE",oracle,
            "ORACLE_BYTES",row["oracle_bytes"],
            "GAIN",row["gain_vs_adaptive"],
            flush=True,
        )
        for label,_ in CONFIGS:
            m=measured[label]
            print(
                "EXP118_CFG",name,label,
                "BYTES",m["archive_bytes"],
                "COMP",m["comp_seconds"],
                "DEC",m["dec_seconds"],
                flush=True,
            )

    raw=sum(r["raw_bytes"] for r in rows)
    adaptive=sum(r["measured"]["adaptive"]["archive_bytes"] for r in rows)
    oracle=sum(r["oracle_bytes"] for r in rows)
    fixed={
        label:sum(r["measured"][label]["archive_bytes"] for r in rows)
        for label,_ in CONFIGS
    }

    result={
        "experiment":"EXP-118A",
        "purpose":"long-context-scale-decomposition",
        "rows":rows,
        "aggregate":{
            "raw_bytes":raw,
            "adaptive_bytes":adaptive,
            "adaptive_ratio":adaptive/raw,
            "oracle_bytes":oracle,
            "oracle_ratio":oracle/raw,
            "gain_vs_adaptive":adaptive-oracle,
            "fixed_totals":fixed,
        },
    }
    Path("exp118_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert len(rows)==4
    assert adaptive==36100213
    assert all(
        m["sha_pass"]
        for r in rows
        for m in r["measured"].values()
    )

    a=result["aggregate"]
    print(
        "EXP118_COMPLETE",
        "ADAPTIVE",a["adaptive_bytes"],
        "ORACLE",a["oracle_bytes"],
        "GAIN",a["gain_vs_adaptive"],
        "ORACLE_RATIO",a["oracle_ratio"],
        flush=True,
    )

if __name__=="__main__":
    main()
