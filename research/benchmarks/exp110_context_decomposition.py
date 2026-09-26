#!/usr/bin/env python3
"""
EXP-110 — Parent vs Inner Context Decomposition

Research-only.

Separates the two effects that EXP-109 changed together:
- K75 parent/grain size;
- inner AUR2 chunk/context size.

All non-baseline research rows force one K75 grain per parent so that parent
size and inner AUR2 context can be varied independently.

The normal/default decoder is used for every archive, proving self-description.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path.cwd()
FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]

CONFIGS=[
    {"label":"baseline-adaptive","parent_kib":0,"inner_kib":0,"force":0},
    {"label":"p1024-i512","parent_kib":1024,"inner_kib":512,"force":1},
    {"label":"p2048-i512","parent_kib":2048,"inner_kib":512,"force":1},
    {"label":"p4096-i512","parent_kib":4096,"inner_kib":512,"force":1},
    {"label":"p8192-i512","parent_kib":8192,"inner_kib":512,"force":1},
    {"label":"p4096-i1024","parent_kib":4096,"inner_kib":1024,"force":1},
    {"label":"p4096-i2048","parent_kib":4096,"inner_kib":2048,"force":1},
    {"label":"p4096-i4096","parent_kib":4096,"inner_kib":4096,"force":1},
    {"label":"p8192-i4096","parent_kib":8192,"inner_kib":4096,"force":1},
    {"label":"p8192-i8192","parent_kib":8192,"inner_kib":8192,"force":1},
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


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp110_context_decomposition.py NATIVE_K75_CLI")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp110_context_decomposition"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]

    for cfg in CONFIGS:
        raw_total=0
        archive_total=0
        comp_total=0.0
        dec_total=0.0
        per_file=[]

        for name in FILES:
            src=corpus/name
            arc=work/f"{name}.{cfg['label']}.kpf"
            out=work/f"out_{cfg['label']}_{name}"

            cmd=[str(cli),"c",str(src),str(arc),"1"]
            if cfg["parent_kib"]:
                cmd += [
                    str(cfg["parent_kib"]),
                    str(cfg["inner_kib"]),
                    str(cfg["force"]),
                ]

            cp=subprocess.run(
                cmd,check=True,text=True,capture_output=True
            )
            cm=parse_cli(cp.stdout)
            comp=float(cm["SECONDS"])

            if out.exists():
                shutil.rmtree(out)
            dp=subprocess.run(
                [str(cli),"d",str(arc),str(out),"1"],
                check=True,text=True,capture_output=True
            )
            dm=parse_cli(dp.stdout)
            dec=float(dm["SECONDS"])

            restored=out/name
            if not restored.is_file() or sha256(restored)!=sha256(src):
                raise SystemExit(
                    f"SHA mismatch config={cfg['label']} file={name}"
                )

            raw=src.stat().st_size
            ab=arc.stat().st_size
            raw_total += raw
            archive_total += ab
            comp_total += comp
            dec_total += dec
            per_file.append({
                "file":name,
                "raw_bytes":raw,
                "archive_bytes":ab,
                "ratio":ab/raw,
                "comp_seconds":comp,
                "dec_seconds":dec,
            })
            shutil.rmtree(out)

        row={
            **cfg,
            "raw_bytes":raw_total,
            "archive_bytes":archive_total,
            "ratio":archive_total/raw_total,
            "comp_seconds":comp_total,
            "dec_seconds":dec_total,
            "comp_MBps":raw_total/1e6/comp_total,
            "dec_MBps":raw_total/1e6/dec_total,
            "sha_all_pass":True,
            "per_file":per_file,
        }
        rows.append(row)

        print(
            "EXP110_ROW",
            "LABEL",cfg["label"],
            "PARENT_KIB",cfg["parent_kib"],
            "INNER_KIB",cfg["inner_kib"],
            "BYTES",archive_total,
            "RATIO",row["ratio"],
            "COMP_MBPS",row["comp_MBps"],
            "DEC_MBPS",row["dec_MBps"],
            "SHA",True,
            flush=True,
        )

    baseline=rows[0]
    for row in rows:
        row["bytes_vs_baseline"]=row["archive_bytes"]-baseline["archive_bytes"]
        row["ratio_delta_vs_baseline"]=row["ratio"]-baseline["ratio"]

    result={
        "experiment":"EXP-110",
        "purpose":"parent-vs-inner-context-decomposition",
        "rows":rows,
    }
    Path("exp110_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert all(r["raw_bytes"]==211938580 for r in rows)
    assert all(r["sha_all_pass"] for r in rows)
    print("EXP110_DECOMPOSITION_COMPLETE",flush=True)


if __name__=="__main__":
    main()
