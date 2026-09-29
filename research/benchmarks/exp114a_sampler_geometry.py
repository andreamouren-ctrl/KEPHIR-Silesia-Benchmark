#!/usr/bin/env python3
"""
EXP-114A — Bounded Sampler Geometry Study

Research-only diagnostic.

EXP-112 used a distributed stride sample over each quarter. EXP-113 kept the
same 256 KiB total sample budget but concentrated it into four 16 KiB windows
per quarter. That changed context-routing decisions on several real files.

This study keeps the total byte budget fixed at 256 KiB and changes only the
spatial geometry:
  4 x 16 KiB / quarter  (current EXP-113)
  8 x  8 KiB / quarter
 16 x  4 KiB / quarter
 32 x  2 KiB / quarter
 64 x  1 KiB / quarter

Each candidate is compared against the EXP-112 distributed stride signal on
canonical Silesia and the deterministic holdout. No compression policy or
production default is modified.
"""

from pathlib import Path
import json
import math
import shutil
import sys

ROOT=Path.cwd()
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import exp112_adaptive_context_router as E112

MiB=1024*1024

GEOMETRIES=[
    ("g4x16k",4,16*1024),
    ("g8x8k",8,8*1024),
    ("g16x4k",16,4*1024),
    ("g32x2k",32,2*1024),
    ("g64x1k",64,1024),
]


def entropy(data):
    if not data:
        return 0.0
    counts=[0]*256
    for b in data:
        counts[b]+=1
    n=len(data)
    h=0.0
    for c in counts:
        if c:
            p=c/n
            h-=p*math.log2(p)
    return h


def route(spread):
    if spread < 0.10:
        return "ctx8m"
    if spread < 0.20:
        return "ctx4m"
    return "baseline"


def bounded_spread(path,windows_per_quarter,window_bytes):
    data=path.read_bytes()
    if len(data) <= 512*1024:
        return 999.0,0

    quarter_h=[]
    sampled=0

    for q in range(4):
        begin=(len(data)*q)//4
        end=(len(data)*(q+1))//4
        length=end-begin
        counts=[0]*256
        total=0

        for part in range(windows_per_quarter):
            rb=begin+(length*part)//windows_per_quarter
            re=begin+(length*(part+1))//windows_per_quarter
            if re<=rb:
                continue
            want=min(window_bytes,re-rb)
            off=rb+(re-rb-want)//2
            buf=data[off:off+want]
            sampled+=len(buf)
            total+=len(buf)
            for b in buf:
                counts[b]+=1

        h=0.0
        if total:
            for c in counts:
                if c:
                    p=c/total
                    h-=p*math.log2(p)
        quarter_h.append(h)

    return max(quarter_h)-min(quarter_h),sampled


def evaluate_dataset(name,files):
    rows=[]
    stats={
        label:{
            "matches":0,
            "files":0,
            "abs_error_sum":0.0,
            "max_abs_error":0.0,
            "sampled_bytes_max":0,
            "mismatches":[],
        }
        for label,_,_ in GEOMETRIES
    }

    for logical,path in files.items():
        reference=E112.cheap_features(path)["quarter_entropy_spread"]
        expected=route(reference)
        row={
            "file":logical,
            "reference_spread":reference,
            "reference_route":expected,
            "geometries":{},
        }

        for label,wins,wbytes in GEOMETRIES:
            spread,sampled=bounded_spread(path,wins,wbytes)
            selected=route(spread)
            err=abs(spread-reference)
            row["geometries"][label]={
                "spread":spread,
                "route":selected,
                "sampled_bytes":sampled,
                "abs_error":err,
            }
            st=stats[label]
            st["files"]+=1
            st["matches"]+= selected==expected
            st["abs_error_sum"]+=err
            st["max_abs_error"]=max(st["max_abs_error"],err)
            st["sampled_bytes_max"]=max(st["sampled_bytes_max"],sampled)
            if selected!=expected:
                st["mismatches"].append({
                    "file":logical,
                    "reference_route":expected,
                    "selected":selected,
                    "reference_spread":reference,
                    "bounded_spread":spread,
                })

        rows.append(row)

    for st in stats.values():
        st["mean_abs_error"]=st["abs_error_sum"]/max(1,st["files"])

    print("EXP114A_DATASET",name,flush=True)
    for label,st in stats.items():
        print(
            "EXP114A_GEOMETRY",name,label,
            "MATCH",f"{st['matches']}/{st['files']}",
            "MAE",st["mean_abs_error"],
            "MAXERR",st["max_abs_error"],
            "MISMATCHES",len(st["mismatches"]),
            "BUDGET",st["sampled_bytes_max"],
            flush=True,
        )

    return {"dataset":name,"stats":stats,"files":rows}


def main():
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp114a_sampler_geometry"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia={name:corpus/name for name in E112.SILESIA_FILES}
    holdout=E112.make_holdout(work/"holdout")

    datasets=[
        evaluate_dataset("silesia",silesia),
        evaluate_dataset("holdout",holdout),
    ]

    result={
        "experiment":"EXP-114A",
        "purpose":"bounded-sampler-geometry",
        "fixed_total_budget_bytes":256*1024,
        "datasets":datasets,
    }
    Path("exp114a_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert all(
        g["sampled_bytes"] <= 256*1024
        for ds in datasets
        for row in ds["files"]
        for g in row["geometries"].values()
    )

    print("EXP114A_COMPLETE",flush=True)


if __name__=="__main__":
    main()
