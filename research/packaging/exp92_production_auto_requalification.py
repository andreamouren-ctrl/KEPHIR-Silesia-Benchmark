#!/usr/bin/env python3
"""
EXP-92 — Production AUTO Requalification

Runs the native ProductionAutoResolver against the actual product execution
path:
- NativeK75Backend
- KPF1 SMART layout
- KPF1 FLAT layout

The matrix is Router Matrix v1 + v2 holdout (16 workloads). For every workload
the tool also performs full SMART and FLAT compression/extraction and derives
the production oracle from the real archive sizes.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"research"/"packaging"))
import router_matrix_v2 as RM


def logical_bytes(root):
    return sum(
        p.stat().st_size
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def parse_metrics(text):
    out={}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k,v=line.split("=",1)
        out[k.strip()]=v.strip()
    return out


def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp92_production_auto_requalification.py "
            "/path/to/kephir2_production_layout_bench"
        )

    cli=Path(sys.argv[1]).resolve()
    if not cli.exists():
        raise SystemExit("missing production layout benchmark: "+str(cli))

    silesia=ROOT/"corpora"/"silesia"
    if not silesia.exists():
        raise SystemExit("canonical Silesia missing")

    base=ROOT/"exp92_production_auto"
    if base.exists():
        shutil.rmtree(base)
    inputs=base/"inputs"
    runs=base/"runs"
    runs.mkdir(parents=True)

    datasets=RM.materialize_matrix(inputs,silesia)

    rows={}
    correct=0
    total_regret=0
    total_resolve=0.0
    total_probe=0.0
    all_byte_perfect=True

    for name,root in datasets.items():
        work=runs/name
        print("EXP92_BEGIN",name,"RAW",logical_bytes(root),flush=True)

        proc=subprocess.run(
            [str(cli),str(root),str(work)],
            check=True,text=True,capture_output=True
        )
        m=parse_metrics(proc.stdout)

        selected=m["SELECTED"]
        oracle=m["ORACLE"]
        regret=int(m["REGRET_BYTES"])
        smart_ok=int(m["SMART_BYTE_PERFECT"])==1
        flat_ok=int(m["FLAT_BYTE_PERFECT"])==1

        row={
            "raw_bytes":logical_bytes(root),
            "selected_layout":selected,
            "oracle_layout":oracle,
            "smart_bytes":int(m["SMART_BYTES"]),
            "flat_bytes":int(m["FLAT_BYTES"]),
            "regret_bytes":regret,
            "probe_count":int(m["PROBE_COUNT"]),
            "probe_seconds":float(m["PROBE_SECONDS"]),
            "resolve_seconds":float(m["RESOLVE_SECONDS"]),
            "smart_comp_seconds":float(m["SMART_COMP_SECONDS"]),
            "flat_comp_seconds":float(m["FLAT_COMP_SECONDS"]),
            "smart_dec_seconds":float(m["SMART_DEC_SECONDS"]),
            "flat_dec_seconds":float(m["FLAT_DEC_SECONDS"]),
            "smart_byte_perfect":smart_ok,
            "flat_byte_perfect":flat_ok,
        }
        rows[name]=row

        correct += int(selected==oracle)
        total_regret += regret
        total_resolve += row["resolve_seconds"]
        total_probe += row["probe_seconds"]
        all_byte_perfect &= smart_ok and flat_ok

        print(
            "EXP92_DATASET",name,
            "SELECTED",selected,
            "ORACLE",oracle,
            "REGRET",regret,
            "SMART",row["smart_bytes"],
            "FLAT",row["flat_bytes"],
            "PROBES",row["probe_count"],
            "RESOLVE_S",row["resolve_seconds"],
            "BYTE_PERFECT",smart_ok and flat_ok,
            flush=True,
        )

        # Keep only the result metrics, not duplicate extracted corpus trees.
        shutil.rmtree(work)

    aggregate={
        "datasets":len(rows),
        "correct_selections":correct,
        "selection_accuracy":correct/len(rows),
        "total_regret_bytes":total_regret,
        "total_resolve_seconds":total_resolve,
        "total_probe_seconds":total_probe,
        "all_byte_perfect":all_byte_perfect,
    }

    result={
        "experiment":"EXP-92",
        "purpose":"production-auto-requalification",
        "matrix":RM.MATRIX_VERSION,
        "datasets":rows,
        "aggregate":aggregate,
    }

    Path("exp92_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP92_AGGREGATE",json.dumps(aggregate,sort_keys=True),flush=True)

    if not all_byte_perfect:
        raise SystemExit("EXP92 byte-perfect roundtrip failure")

    print("EXP92_BYTE_PERFECT_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
