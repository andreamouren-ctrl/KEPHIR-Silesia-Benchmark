#!/usr/bin/env python3
"""
EXP-109 — Production K75/AUR2 Context Sweep

Research-only. The qualified default remains unchanged.

Compares:
- current adaptive 512 KiB production path;
- fixed 512 KiB context;
- fixed 1 MiB context;
- fixed 2 MiB context;
- fixed 4 MiB context.

Each archive is decoded by the normal/default decoder without passing the
research context, proving that KPF1/K75U/AUR2 remains self-describing.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT=Path.cwd()
FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]
CONTEXTS=[0,512,1024,2048,4096]


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
        raise SystemExit(
            "usage: exp109_production_context_sweep.py NATIVE_K75_CLI"
        )

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp109_context_sweep"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows=[]

    for context in CONTEXTS:
        raw_total=0
        arc_total=0
        comp_total=0.0
        dec_total=0.0
        per_file=[]

        for name in FILES:
            src=corpus/name
            arc=work/f"{name}.ctx{context}.kpf"
            out=work/f"out_{context}_{name}"
            if out.exists():
                shutil.rmtree(out)

            cmd=[str(cli),"c",str(src),str(arc),"1"]
            if context:
                cmd.append(str(context))

            p=subprocess.run(
                cmd,
                check=True,text=True,capture_output=True
            )
            cm=parse_cli(p.stdout)
            comp=float(cm["SECONDS"])

            # Decode deliberately uses the ordinary default path.
            p=subprocess.run(
                [str(cli),"d",str(arc),str(out),"1"],
                check=True,text=True,capture_output=True
            )
            dm=parse_cli(p.stdout)
            dec=float(dm["SECONDS"])

            restored=out/name
            if not restored.is_file() or sha256(restored)!=sha256(src):
                raise SystemExit(
                    f"SHA mismatch context={context} file={name}"
                )

            raw=src.stat().st_size
            ab=arc.stat().st_size
            raw_total+=raw
            arc_total+=ab
            comp_total+=comp
            dec_total+=dec

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
            "context_kib":context,
            "label":"adaptive-default" if context==0 else f"fixed-{context}KiB",
            "raw_bytes":raw_total,
            "archive_bytes":arc_total,
            "ratio":arc_total/raw_total,
            "comp_seconds":comp_total,
            "dec_seconds":dec_total,
            "comp_MBps":raw_total/1e6/comp_total,
            "dec_MBps":raw_total/1e6/dec_total,
            "sha_all_pass":True,
            "per_file":per_file,
        }
        rows.append(row)

        print(
            "EXP109_ROW",
            "CONTEXT_KIB",context,
            "BYTES",arc_total,
            "RATIO",row["ratio"],
            "COMP_MBPS",row["comp_MBps"],
            "DEC_MBPS",row["dec_MBps"],
            "SHA",True,
            flush=True,
        )

    baseline=next(r for r in rows if r["context_kib"]==0)
    for r in rows:
        r["bytes_vs_adaptive"]=r["archive_bytes"]-baseline["archive_bytes"]
        r["ratio_delta_vs_adaptive"]=r["ratio"]-baseline["ratio"]

    result={
        "experiment":"EXP-109",
        "purpose":"production-k75-aur2-context-sweep",
        "note":"research-only context override; decoder uses default path",
        "rows":rows,
    }
    Path("exp109_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert all(r["raw_bytes"]==211938580 for r in rows)
    assert all(r["sha_all_pass"] for r in rows)
    print("EXP109_SWEEP_COMPLETE",flush=True)


if __name__=="__main__":
    main()
