#!/usr/bin/env python3
"""
KASH-04: conservative depth-2 recovery predictor with leave-one-source-out validation.

The model is deliberately tiny:
- deterministic PCM-only features from KASH-02;
- binary decision tree, max depth 2;
- false split byte cost is multiplied by a conservative penalty;
- no encoded-size lookup is used by the candidate production decision.

Research oracle encodes both 1 s / 2 s options only to provide labels and an upper bound.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import kash02_reset_predictor as k2

RATE=48_000
CH=2
BITS=16
FB=CH*(BITS//8)
OUT=Path("results/audio/kash04")
FALSE_SPLIT_PENALTY=4.0
MAX_DEPTH=2
MIN_LEAF=5
THRESHOLD_POINTS=10


def parse_source(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source must be name=path")
    name,path=value.split("=",1)
    return name,Path(path)


def penalized_delta(row):
    d=float(row["split_delta_bytes"])
    return d if d < 0 else FALSE_SPLIT_PENALTY*d


def leaf(rows):
    split_cost=sum(penalized_delta(r) for r in rows)
    action=split_cost < 0.0
    return {"leaf":True,"split":action}, (split_cost if action else 0.0)


def threshold_candidates(values):
    vals=sorted(set(float(v) for v in values))
    if len(vals)<=1:
        return vals
    if len(vals)<=THRESHOLD_POINTS:
        return [(a+b)*0.5 for a,b in zip(vals,vals[1:])]
    out=[]
    for i in range(1,THRESHOLD_POINTS):
        pos=i*(len(vals)-1)/THRESHOLD_POINTS
        j=int(pos)
        if j+1<len(vals):
            out.append((vals[j]+vals[j+1])*0.5)
    return sorted(set(out))


def predict_cmp(value,op,threshold):
    return value>=threshold if op=="ge" else value<=threshold


def fit_tree(rows,depth=MAX_DEPTH):
    base_tree,base_cost=leaf(rows)
    if depth<=0 or len(rows)<2*MIN_LEAF:
        return base_tree,base_cost

    features=sorted(rows[0]["features"].keys())
    best=(base_cost,base_tree)

    for feature in features:
        values=[r["features"][feature] for r in rows]
        for threshold in threshold_candidates(values):
            for op in ("ge","le"):
                yes=[r for r in rows if predict_cmp(r["features"][feature],op,threshold)]
                no=[r for r in rows if not predict_cmp(r["features"][feature],op,threshold)]
                if len(yes)<MIN_LEAF or len(no)<MIN_LEAF:
                    continue
                yes_tree,yes_cost=fit_tree(yes,depth-1)
                no_tree,no_cost=fit_tree(no,depth-1)
                cost=yes_cost+no_cost
                node={
                    "leaf":False,
                    "feature":feature,
                    "op":op,
                    "threshold":threshold,
                    "yes":yes_tree,
                    "no":no_tree,
                }
                key=(cost,feature,op,threshold)
                best_key=(best[0],
                          best[1].get("feature",""),
                          best[1].get("op",""),
                          best[1].get("threshold",0.0))
                if key<best_key:
                    best=(cost,node)

    return best[1],best[0]


def tree_predict(tree,features):
    node=tree
    while not node["leaf"]:
        branch=predict_cmp(
            features[node["feature"]],
            node["op"],
            float(node["threshold"]),
        )
        node=node["yes"] if branch else node["no"]
    return bool(node["split"])


def choose_segments(pcm,total,tree):
    raw=np.frombuffer(pcm,dtype="<i2")
    frames=raw.reshape(-1,CH).astype(np.int32)
    start=0
    entries=[]
    decision_s=0.0
    one=two=0

    while start<total:
        remaining=total-start
        if remaining<2*RATE:
            count=remaining
            one+=1
        else:
            t0=time.perf_counter()
            feats=k2.boundary_features(frames,start)
            split=tree_predict(tree,feats)
            decision_s+=time.perf_counter()-t0
            count=RATE if split else 2*RATE
            if split: one+=1
            else: two+=1
        entries.append((start,count))
        start+=count

    return entries,decision_s,one,two


def prepare_source(name,path,exe):
    pcm=path.read_bytes()
    if len(pcm)%FB:
        raise RuntimeError(f"{name}: unaligned PCM")
    total=len(pcm)//FB

    cache,positions,oracle_search_s,oracle_encode_count=k2.build_oracle_cache(pcm,exe)
    oracle_objective,oracle_entries=k2.oracle_dp(cache,positions)
    rows=k2.make_label_rows(pcm,cache,total)
    for row in rows:
        row["source"]=name

    fixed_encoded,fixed_encode_s=k2.encode_segments(
        pcm,k2.fixed_segments(total),exe
    )

    source_out=OUT/name
    source_out.mkdir(parents=True,exist_ok=True)
    old_out=k2.OUT
    k2.OUT=source_out
    try:
        fixed=k2.write_verify("fixed_2s",fixed_encoded,pcm,exe)
        oracle=k2.write_verify("oracle_1_2s",oracle_entries,pcm,exe)
    finally:
        k2.OUT=old_out

    fixed["encode_seconds"]=fixed_encode_s
    oracle["search_encode_seconds"]=oracle_search_s
    oracle["oracle_encode_count"]=oracle_encode_count
    oracle["objective_bytes_excluding_fixed_container"]=oracle_objective

    return {
        "name":name,
        "pcm":pcm,
        "total":total,
        "rows":rows,
        "fixed":fixed,
        "oracle":oracle,
        "raw_bytes":len(pcm),
    }


def evaluate_fold(held,sources,exe):
    train_rows=[]
    for s in sources:
        if s["name"]!=held["name"]:
            train_rows.extend(s["rows"])

    fit_t0=time.perf_counter()
    tree,training_objective=fit_tree(train_rows)
    fit_s=time.perf_counter()-fit_t0

    segments,decision_s,one,two=choose_segments(
        held["pcm"],held["total"],tree
    )
    encoded,encode_s=k2.encode_segments(held["pcm"],segments,exe)

    old_out=k2.OUT
    k2.OUT=OUT/held["name"]
    try:
        predictor=k2.write_verify(
            "kash04_loso_predictor",encoded,held["pcm"],exe
        )
    finally:
        k2.OUT=old_out

    predictor.update({
        "encode_seconds":encode_s,
        "decision_seconds":decision_s,
        "count_1s":one,
        "count_2s":two,
    })

    fixed_b=held["fixed"]["bytes"]
    oracle_b=held["oracle"]["bytes"]
    pred_b=predictor["bytes"]
    available=fixed_b-oracle_b
    gain=fixed_b-pred_b

    return {
        "held_out":held["name"],
        "tree":tree,
        "training_objective":training_objective,
        "training_seconds":fit_s,
        "fixed_2s":held["fixed"],
        "oracle":held["oracle"],
        "predictor":predictor,
        "oracle_gain_bytes":available,
        "predictor_gain_bytes":gain,
        "predictor_delta_percent_vs_fixed":100.0*(pred_b-fixed_b)/fixed_b,
        "oracle_gain_recovered_percent":(
            100.0*gain/available if available>0 else 0.0
        ),
        "production_candidate_duplicate_encodes":0,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--source",action="append",type=parse_source,required=True)
    args=ap.parse_args()

    OUT.mkdir(parents=True,exist_ok=True)
    sources=[prepare_source(name,path,args.kephir) for name,path in args.source]
    folds=[evaluate_fold(s,sources,args.kephir) for s in sources]

    all_rows=[]
    for s in sources:
        all_rows.extend(s["rows"])
    final_tree,final_objective=fit_tree(all_rows)

    fixed_total=sum(f["fixed_2s"]["bytes"] for f in folds)
    oracle_total=sum(f["oracle"]["bytes"] for f in folds)
    predictor_total=sum(f["predictor"]["bytes"] for f in folds)
    oracle_gain=fixed_total-oracle_total
    predictor_gain=fixed_total-predictor_total
    positive=sum(1 for f in folds if f["predictor_gain_bytes"]>0)
    non_regressing=sum(1 for f in folds if f["predictor_gain_bytes"]>=0)
    worst=max(f["predictor_delta_percent_vs_fixed"] for f in folds)

    agg={
        "fixed_2s_bytes":fixed_total,
        "oracle_bytes":oracle_total,
        "predictor_bytes":predictor_total,
        "oracle_gain_bytes":oracle_gain,
        "predictor_gain_bytes":predictor_gain,
        "predictor_delta_percent_vs_fixed":100.0*(predictor_total-fixed_total)/fixed_total,
        "oracle_gain_recovered_percent":(
            100.0*predictor_gain/oracle_gain if oracle_gain>0 else 0.0
        ),
        "positive_sources":positive,
        "non_regressing_sources":non_regressing,
        "source_count":len(folds),
        "worst_source_regression_percent":worst,
    }

    result={
        "experiment":"KASH-04 conservative depth-2 LOSO recovery predictor",
        "false_split_penalty":FALSE_SPLIT_PENALTY,
        "max_depth":MAX_DEPTH,
        "min_leaf":MIN_LEAF,
        "folds":folds,
        "aggregate":agg,
        "final_tree_fit_all_sources":final_tree,
        "final_training_objective":final_objective,
        "production_candidate_duplicate_encodes":0,
    }

    result["promotion_candidate"]=(
        predictor_total<fixed_total
        and non_regressing==len(folds)
        and agg["oracle_gain_recovered_percent"]>=25.0
    )

    (OUT/"KASH04_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KASH04_PASS")
    print(
        "AGGREGATE",
        "fixed",fixed_total,
        "oracle",oracle_total,
        "predictor",predictor_total,
        "gain",predictor_gain,
        "recovered_pct",f"{agg['oracle_gain_recovered_percent']:.3f}",
        "non_regressing",f"{non_regressing}/{len(folds)}",
        "promotion_candidate",result["promotion_candidate"],
    )
    print("FINAL_TREE",json.dumps(final_tree,separators=(",",":")))
    for f in folds:
        print(
            "FOLD",f["held_out"],
            "fixed",f["fixed_2s"]["bytes"],
            "oracle",f["oracle"]["bytes"],
            "predictor",f["predictor"]["bytes"],
            "gain",f["predictor_gain_bytes"],
            "delta_pct",f"{f['predictor_delta_percent_vs_fixed']:.6f}",
            "recovered_pct",f"{f['oracle_gain_recovered_percent']:.3f}",
            "decision_s",f"{f['predictor']['decision_seconds']:.6f}",
        )


if __name__=="__main__":
    main()
