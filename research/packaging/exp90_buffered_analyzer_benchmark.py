#!/usr/bin/env python3
"""
EXP-90 — Native Planner Gate Parity & Performance

Validates the production C++ ContentAnalyzer -> CompressionPlanner ->
GlobalRouter initial AUTO action on Router Matrix v1 + holdout v2.

The measured planner path is entirely native. Python is used only to
materialize deterministic workloads and independently verify expected EXP-88
gate features/actions.
"""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
sys.path.insert(0,str(ROOT/"research"/"packaging"))

import kephir_final as K
import router_matrix_v2 as RM

OUT=ROOT/"exp90_buffered_analyzer"
INPUTS=OUT/"inputs"

MIN_AVG=512*1024
MIN_REPEATABLE=0.60
MAX_DOMINANT=0.75
STAGE1=512*1024
SMALL_FULL=1024*1024


def expected_features(root):
    by_files={}
    by_bytes={}
    total=0
    count=0
    for p in K.collect_directory(root):
        data=p.read_bytes()
        group=K.classify(data)
        by_files[group]=by_files.get(group,0)+1
        by_bytes[group]=by_bytes.get(group,0)+len(data)
        total+=len(data)
        count+=1

    groups=len(by_files)
    multi=sum(1 for n in by_files.values() if n>=2)
    repeatable=sum(by_bytes[g] for g,n in by_files.items() if n>=2)
    dominant=max(by_bytes.values(),default=0)
    avg=total/count if count else 0.0

    return {
        "logical_bytes":total,
        "file_count":count,
        "groups":groups,
        "multi_file_groups":multi,
        "repeatable_fraction":repeatable/total if total else 0.0,
        "dominant_fraction":dominant/total if total else 0.0,
        "average_file_bytes":avg,
    }


def expected_action(f):
    if f["file_count"]==0 or f["groups"]<=1:
        return "final","flat",0

    smart_candidate=(
        f["average_file_bytes"]>=MIN_AVG
        and f["repeatable_fraction"]>=MIN_REPEATABLE
        and f["dominant_fraction"]<=MAX_DOMINANT
    )
    if not smart_candidate:
        return "final","flat",0

    target=f["logical_bytes"] if f["logical_bytes"]<=SMALL_FULL else min(STAGE1,f["logical_bytes"])
    return "probe","smart",target


def parse_native(stdout):
    rows={}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts=line.split("\t")
        if len(parts)!=12:
            raise RuntimeError(f"unexpected native planner line: {line!r}")
        (
            path,action,layout,probe,logical,files,groups,multi,
            repeatable,dominant,avg,elapsed_ms
        )=parts
        rows[path]={
            "action":action,
            "layout":layout,
            "probe_bytes":int(probe),
            "logical_bytes":int(logical),
            "file_count":int(files),
            "groups":int(groups),
            "multi_file_groups":int(multi),
            "repeatable_fraction":float(repeatable),
            "dominant_fraction":float(dominant),
            "average_file_bytes":float(avg),
            "elapsed_ms":float(elapsed_ms),
        }
    return rows


def close(a,b,tol=1e-12):
    return abs(a-b)<=tol


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp90_buffered_analyzer_benchmark.py /path/to/kephir2_planner_dump")

    exe=Path(sys.argv[1]).resolve()
    if not exe.exists():
        raise SystemExit(f"missing native planner utility: {exe}")

    datasets=RM.materialize_matrix(INPUTS,ROOT/"corpora"/"silesia")
    paths=[str(Path(p).resolve()) for p in datasets.values()]

    t0=time.perf_counter()
    proc=subprocess.run([str(exe),*paths],check=True,text=True,capture_output=True)
    wall_s=time.perf_counter()-t0
    native=parse_native(proc.stdout)

    results={}
    action_matches=0
    feature_mismatches=0
    total_native_ms=0.0

    for name,root in datasets.items():
        key=str(Path(root).resolve())
        row=native[key]
        exp=expected_features(root)
        exp_action,exp_layout,exp_probe=expected_action(exp)

        action_ok=(
            row["action"]==exp_action
            and row["probe_bytes"]==exp_probe
            and (row["layout"]==exp_layout if exp_action=="final" else True)
        )
        action_matches+=int(action_ok)

        checks={
            "logical_bytes":row["logical_bytes"]==exp["logical_bytes"],
            "file_count":row["file_count"]==exp["file_count"],
            "groups":row["groups"]==exp["groups"],
            "multi_file_groups":row["multi_file_groups"]==exp["multi_file_groups"],
            "repeatable_fraction":close(row["repeatable_fraction"],exp["repeatable_fraction"]),
            "dominant_fraction":close(row["dominant_fraction"],exp["dominant_fraction"]),
            "average_file_bytes":close(row["average_file_bytes"],exp["average_file_bytes"]),
        }
        features_ok=all(checks.values())
        feature_mismatches+=int(not features_ok)
        total_native_ms+=row["elapsed_ms"]

        results[name]={
            "expected_action":exp_action,
            "expected_layout":exp_layout,
            "expected_probe_bytes":exp_probe,
            "native":row,
            "action_ok":action_ok,
            "features_ok":features_ok,
            "feature_checks":checks,
        }

        print(
            "EXP90_DATASET",name,
            "ACTION",row["action"],
            "LAYOUT",row["layout"],
            "PROBE",row["probe_bytes"],
            "EXPECTED",exp_action,exp_layout,exp_probe,
            "ACTION_OK",action_ok,
            "FEATURES_OK",features_ok,
            "NATIVE_MS",row["elapsed_ms"],
            flush=True,
        )

    aggregate={
        "datasets":len(datasets),
        "action_matches":action_matches,
        "action_accuracy":action_matches/len(datasets),
        "feature_mismatches":feature_mismatches,
        "native_planning_ms_sum":total_native_ms,
        "native_planning_s_sum":total_native_ms/1000.0,
        "native_process_wall_s":wall_s,
    }

    out={
        "experiment":"EXP-90",
        "change":"buffered-native-analyzer-performance",
        "aggregate":aggregate,
        "datasets":results,
    }
    Path("exp90_results.json").write_text(json.dumps(out,indent=2,sort_keys=True))

    print("EXP90_AGGREGATE",json.dumps(aggregate,sort_keys=True),flush=True)

    if action_matches!=len(datasets):
        raise SystemExit("native EXP-88 action parity failed")
    if feature_mismatches:
        raise SystemExit("native groupability feature parity failed")

    print("EXP90_NATIVE_PARITY_PASS",flush=True)


if __name__=="__main__":
    main()
