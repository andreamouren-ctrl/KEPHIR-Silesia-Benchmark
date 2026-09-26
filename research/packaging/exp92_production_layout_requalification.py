#!/usr/bin/env python3
"""
EXP-92 — Production Layout Requalification

Runs the actual native ProductionAutoResolver and NativeK75 KPF1 execution
path over Router Matrix v1 + holdout v2.

For every workload the C++ benchmark:
- resolves AUTO using production probes;
- compresses full SMART and FLAT archives;
- extracts both;
- verifies byte-perfect trees;
- records production oracle and selection regret.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"research"/"packaging"))
import router_matrix_v2 as RM


def parse(text):
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
            "usage: exp92_production_layout_requalification.py "
            "/path/to/kephir2_production_layout_bench"
        )

    exe=Path(sys.argv[1]).resolve()
    if not exe.exists():
        raise SystemExit("missing production layout benchmark: "+str(exe))

    inputs=ROOT/"exp92_inputs"
    outputs=ROOT/"exp92_outputs"
    if outputs.exists():
        shutil.rmtree(outputs)
    outputs.mkdir(parents=True)

    datasets=RM.materialize_matrix(inputs,ROOT/"corpora"/"silesia")

    rows={}
    correct=0
    regret=0
    resolve_s=0.0
    smart_comp_s=flat_comp_s=0.0
    smart_dec_s=flat_dec_s=0.0

    for name,root in datasets.items():
        out=outputs/name
        t0=time.perf_counter()
        p=subprocess.run(
            [str(exe),str(root),str(out)],
            check=True,text=True,capture_output=True
        )
        wall=time.perf_counter()-t0
        m=parse(p.stdout)

        selected=m["SELECTED"]
        oracle=m["ORACLE"]
        row={
            "selected":selected,
            "oracle":oracle,
            "smart_bytes":int(m["SMART_BYTES"]),
            "flat_bytes":int(m["FLAT_BYTES"]),
            "regret_bytes":int(m["REGRET_BYTES"]),
            "probe_count":int(m["PROBE_COUNT"]),
            "probe_seconds":float(m["PROBE_SECONDS"]),
            "resolve_seconds":float(m["RESOLVE_SECONDS"]),
            "smart_comp_seconds":float(m["SMART_COMP_SECONDS"]),
            "flat_comp_seconds":float(m["FLAT_COMP_SECONDS"]),
            "smart_dec_seconds":float(m["SMART_DEC_SECONDS"]),
            "flat_dec_seconds":float(m["FLAT_DEC_SECONDS"]),
            "smart_byte_perfect":int(m["SMART_BYTE_PERFECT"])==1,
            "flat_byte_perfect":int(m["FLAT_BYTE_PERFECT"])==1,
            "wall_seconds":wall,
        }
        rows[name]=row

        ok=(
            selected==oracle
            and row["regret_bytes"]==0
            and row["smart_byte_perfect"]
            and row["flat_byte_perfect"]
        )
        correct+=int(selected==oracle)
        regret+=row["regret_bytes"]
        resolve_s+=row["resolve_seconds"]
        smart_comp_s+=row["smart_comp_seconds"]
        flat_comp_s+=row["flat_comp_seconds"]
        smart_dec_s+=row["smart_dec_seconds"]
        flat_dec_s+=row["flat_dec_seconds"]

        print(
            "EXP92_DATASET",name,
            "SELECTED",selected,
            "ORACLE",oracle,
            "SMART",row["smart_bytes"],
            "FLAT",row["flat_bytes"],
            "REGRET",row["regret_bytes"],
            "PROBES",row["probe_count"],
            "RESOLVE_S",row["resolve_seconds"],
            "PASS",ok,
            flush=True,
        )

    n=len(rows)
    aggregate={
        "datasets":n,
        "correct":correct,
        "accuracy":correct/n if n else 0.0,
        "regret_bytes":regret,
        "resolve_seconds":resolve_s,
        "smart_comp_seconds":smart_comp_s,
        "flat_comp_seconds":flat_comp_s,
        "smart_dec_seconds":smart_dec_s,
        "flat_dec_seconds":flat_dec_s,
        "byte_perfect_all":all(
            r["smart_byte_perfect"] and r["flat_byte_perfect"]
            for r in rows.values()
        ),
    }

    result={
        "experiment":"EXP-92",
        "purpose":"production-layout-requalification",
        "matrix":RM.MATRIX_VERSION,
        "aggregate":aggregate,
        "datasets":rows,
    }
    Path("exp92_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP92_AGGREGATE",json.dumps(aggregate,sort_keys=True),flush=True)
    if not aggregate["byte_perfect_all"]:
        raise SystemExit("EXP92 byte-perfect failure")
    print("EXP92_BYTE_PERFECT_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
