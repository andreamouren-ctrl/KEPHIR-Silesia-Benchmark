#!/usr/bin/env python3
"""
KASH-04: conservative adaptive recovery with fixed 2-second macro-windows.

Each complete 2-second macro-window is either:
- encoded as one 2-second recovery packet; or
- split into two 1-second recovery packets.

Window boundaries never shift, so every prediction corresponds exactly to the
local compression decision used to train/validate the rule.

Rule search:
- cheap PCM-only KASH-02 features;
- one condition or a conservative two-condition AND;
- thresholds from source-spanning quantiles;
- training candidates that regress any training source are rejected;
- leave-one-source-out validation measures generalization of the procedure.

The research oracle may encode duplicate candidates. The candidate production
path performs zero duplicate candidate encodes.
"""
import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import kash02_reset_predictor as k2

RATE=48_000
CH=2
BITS=16
FB=CH*(BITS//8)
META=64
OUT=Path("results/audio/kash04")


def parse_source(value: str):
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source must be name=path")
    name, raw=value.split("=",1)
    if not name or not raw:
        raise argparse.ArgumentTypeError("--source must be name=path")
    return name,Path(raw)


def macro_rows(name: str, pcm: bytes, cache):
    total=len(pcm)//FB
    raw=np.frombuffer(pcm,dtype="<i2")
    frames=raw.reshape(-1,CH).astype(np.int32)

    rows=[]
    for start in range(0,total-2*RATE+1,2*RATE):
        mid=start+RATE
        end=start+2*RATE
        one_a=cache[(start,mid)]
        one_b=cache[(mid,end)]
        two=cache[(start,end)]

        joined=len(two)+META
        split=len(one_a)+META+len(one_b)+META
        gain=joined-split  # positive => splitting saves bytes

        rows.append({
            "source":name,
            "start":start,
            "gain_bytes":int(gain),
            "features":k2.boundary_features(frames,start),
        })
    return rows


def thresholds(values):
    vals=np.asarray(values,dtype=np.float64)
    if vals.size==0:
        return [0.0]
    qs=np.quantile(vals,[0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.95])
    return sorted(set(float(x) for x in qs))


def condition(row, cond):
    v=row["features"][cond["feature"]]
    return v>=cond["threshold"] if cond["op"]=="ge" else v<=cond["threshold"]


def predict(row, rule):
    return all(condition(row,c) for c in rule["conditions"])


def source_gains(rows, rule):
    gains={}
    split_count=0
    for r in rows:
        if predict(r,rule):
            gains[r["source"]]=gains.get(r["source"],0)+r["gain_bytes"]
            split_count+=1
        else:
            gains.setdefault(r["source"],0)
    return gains,split_count


def primitive_conditions(rows):
    features=sorted(rows[0]["features"].keys())
    out=[]
    for feature in features:
        vals=[r["features"][feature] for r in rows]
        for threshold in thresholds(vals):
            out.append({"feature":feature,"op":"ge","threshold":threshold})
            out.append({"feature":feature,"op":"le","threshold":threshold})
    return out


def select_rule(rows):
    if not rows:
        return {"conditions":[],"kind":"never_split","train_gain_bytes":0}

    sources=sorted({r["source"] for r in rows})
    primitives=primitive_conditions(rows)

    candidates=[]
    for c in primitives:
        candidates.append({"conditions":[c],"kind":"single"})

    # Conservative two-feature conjunction. Avoid duplicate conditions on the
    # same feature so the rule remains interpretable and low-cost.
    for a,b in combinations(primitives,2):
        if a["feature"]==b["feature"]:
            continue
        candidates.append({"conditions":[a,b],"kind":"and2"})

    best={
        "conditions":[],
        "kind":"never_split",
        "train_gain_bytes":0,
        "train_min_source_gain_bytes":0,
        "train_split_count":0,
    }
    best_key=(0,0,0,0)

    for rule in candidates:
        gains,split_count=source_gains(rows,rule)
        per_source=[gains.get(s,0) for s in sources]

        # Hard conservative gate: no training source may regress.
        if any(g<0 for g in per_source):
            continue

        total=sum(per_source)
        if total<=0:
            continue

        min_gain=min(per_source)
        complexity=len(rule["conditions"])

        # Maximize actual bytes saved, then worst-source gain. If two rules are
        # otherwise equivalent, prefer fewer splits and a simpler rule.
        key=(total,min_gain,-split_count,-complexity)
        if key>best_key:
            best_key=key
            best={
                **rule,
                "train_gain_bytes":int(total),
                "train_min_source_gain_bytes":int(min_gain),
                "train_split_count":int(split_count),
            }

    return best


def segments_for_rule(pcm: bytes, rule):
    total=len(pcm)//FB
    frames=np.frombuffer(pcm,dtype="<i2").reshape(-1,CH).astype(np.int32)
    segments=[]
    split_windows=0

    start=0
    while start<total:
        remaining=total-start
        if remaining<2*RATE:
            segments.append((start,remaining))
            break

        row={
            "source":"production",
            "start":start,
            "gain_bytes":0,
            "features":k2.boundary_features(frames,start),
        }
        if rule["conditions"] and predict(row,rule):
            segments.append((start,RATE))
            segments.append((start+RATE,RATE))
            split_windows+=1
        else:
            segments.append((start,2*RATE))
        start+=2*RATE

    return segments,split_windows


def build_source(name: str, path: Path, exe: Path):
    pcm=path.read_bytes()
    if len(pcm)%FB:
        raise RuntimeError(f"{name}: PCM not frame aligned")
    total=len(pcm)//FB
    cache,positions,oracle_s,oracle_n=k2.build_oracle_cache(pcm,exe)
    rows=macro_rows(name,pcm,cache)
    return {
        "name":name,
        "pcm":pcm,
        "total":total,
        "cache":cache,
        "positions":positions,
        "oracle_search_seconds":oracle_s,
        "oracle_encode_count":oracle_n,
        "rows":rows,
    }


def evaluate_source(src, rule, exe: Path):
    name=src["name"]
    pcm=src["pcm"]
    total=src["total"]

    fixed_segments=k2.fixed_segments(total)
    pred_segments,split_windows=segments_for_rule(pcm,rule)

    # Exact macro-window oracle: choose the cheaper representation for each
    # independent 2-second window; final tail remains unchanged.
    oracle_entries=[]
    full=total//(2*RATE)
    for wi in range(full):
        start=wi*2*RATE
        mid=start+RATE
        end=start+2*RATE
        cache=src["cache"]
        one_a=cache[(start,mid)]
        one_b=cache[(mid,end)]
        two=cache[(start,end)]
        joined_cost=len(two)+META
        split_cost=len(one_a)+META+len(one_b)+META
        if split_cost<joined_cost:
            oracle_entries.append((start,RATE,one_a))
            oracle_entries.append((mid,RATE,one_b))
        else:
            oracle_entries.append((start,2*RATE,two))

    tail_start=full*2*RATE
    if tail_start<total:
        tail_end=total
        payload=src["cache"][(tail_start,tail_end)]
        oracle_entries.append((tail_start,tail_end-tail_start,payload))

    fixed_encoded,fixed_encode_s=k2.encode_segments(pcm,fixed_segments,exe)
    pred_encoded,pred_encode_s=k2.encode_segments(pcm,pred_segments,exe)

    source_out=OUT/name
    source_out.mkdir(parents=True,exist_ok=True)
    old_out=k2.OUT
    k2.OUT=source_out
    try:
        fixed=k2.write_verify("fixed_2s",fixed_encoded,pcm,exe)
        predictor=k2.write_verify("predictor_macro",pred_encoded,pcm,exe)
        oracle=k2.write_verify("oracle_macro",oracle_entries,pcm,exe)
    finally:
        k2.OUT=old_out

    fixed["encode_seconds"]=fixed_encode_s
    predictor["encode_seconds"]=pred_encode_s
    predictor["split_windows"]=split_windows
    oracle["research_search_seconds"]=src["oracle_search_seconds"]

    return {
        "name":name,
        "fixed":fixed,
        "predictor":predictor,
        "oracle":oracle,
        "predictor_gain_bytes":fixed["bytes"]-predictor["bytes"],
        "oracle_gain_bytes":fixed["bytes"]-oracle["bytes"],
        "production_candidate_duplicate_encodes":0,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--source",action="append",type=parse_source,required=True)
    args=ap.parse_args()

    OUT.mkdir(parents=True,exist_ok=True)
    sources=[build_source(name,path,args.kephir) for name,path in args.source]

    # Leave-one-source-out validation of the rule-selection procedure.
    folds=[]
    all_names=[s["name"] for s in sources]
    for held in sources:
        train_rows=[
            row
            for src in sources if src["name"]!=held["name"]
            for row in src["rows"]
        ]
        rule=select_rule(train_rows)
        held_gains,_=source_gains(held["rows"],rule)
        held_gain=held_gains.get(held["name"],0)
        folds.append({
            "held_out":held["name"],
            "rule":rule,
            "held_out_local_gain_bytes":int(held_gain),
        })

    final_rows=[row for src in sources for row in src["rows"]]
    final_rule=select_rule(final_rows)

    evaluated=[evaluate_source(src,final_rule,args.kephir) for src in sources]

    fixed_total=sum(x["fixed"]["bytes"] for x in evaluated)
    predictor_total=sum(x["predictor"]["bytes"] for x in evaluated)
    oracle_total=sum(x["oracle"]["bytes"] for x in evaluated)
    gains=[x["predictor_gain_bytes"] for x in evaluated]
    heldout=[f["held_out_local_gain_bytes"] for f in folds]

    result={
        "experiment":"KASH-04 conservative fixed-macro adaptive recovery",
        "sources":all_names,
        "leave_one_source_out":folds,
        "final_rule":final_rule,
        "results":evaluated,
        "aggregate":{
            "fixed_bytes":fixed_total,
            "predictor_bytes":predictor_total,
            "oracle_bytes":oracle_total,
            "predictor_gain_bytes":fixed_total-predictor_total,
            "oracle_gain_bytes":fixed_total-oracle_total,
            "oracle_gain_recovered_percent":(
                100.0*(fixed_total-predictor_total)/(fixed_total-oracle_total)
                if fixed_total>oracle_total else 0.0
            ),
            "worst_source_gain_bytes":min(gains) if gains else 0,
            "worst_heldout_local_gain_bytes":min(heldout) if heldout else 0,
        },
        "production_candidate_duplicate_encodes":0,
    }

    # This is a research promotion gate for the MODELING PROCEDURE, not final
    # product deployment. Product deployment still requires a fresh corpus.
    result["procedure_promotion_candidate"]=(
        result["aggregate"]["predictor_gain_bytes"]>0
        and result["aggregate"]["worst_source_gain_bytes"]>=0
        and result["aggregate"]["worst_heldout_local_gain_bytes"]>=0
    )

    (OUT/"KASH04_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KASH04_PASS")
    print("FINAL_RULE",json.dumps(final_rule,sort_keys=True))
    print(
        "AGGREGATE",
        "fixed",fixed_total,
        "predictor",predictor_total,
        "oracle",oracle_total,
        "gain",result["aggregate"]["predictor_gain_bytes"],
        "oracle_gain",result["aggregate"]["oracle_gain_bytes"],
        "recovered_pct",f"{result['aggregate']['oracle_gain_recovered_percent']:.3f}",
        "worst_source_gain",result["aggregate"]["worst_source_gain_bytes"],
        "worst_heldout_gain",result["aggregate"]["worst_heldout_local_gain_bytes"],
        "procedure_candidate",result["procedure_promotion_candidate"],
    )
    for f in folds:
        print(
            "LOSO",
            "held_out",f["held_out"],
            "gain",f["held_out_local_gain_bytes"],
            "rule",json.dumps(f["rule"],sort_keys=True),
        )
    for r in evaluated:
        print(
            "SOURCE",
            r["name"],
            "fixed",r["fixed"]["bytes"],
            "predictor",r["predictor"]["bytes"],
            "oracle",r["oracle"]["bytes"],
            "gain",r["predictor_gain_bytes"],
            "oracle_gain",r["oracle_gain_bytes"],
            "splits",r["predictor"]["split_windows"],
        )


if __name__=="__main__":
    main()
