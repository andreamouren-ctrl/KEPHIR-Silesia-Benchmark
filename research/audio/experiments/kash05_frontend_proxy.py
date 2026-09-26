#!/usr/bin/env python3
"""
KASH-05: codec-aware adaptive recovery using the canonical KMRL frontend size
as a cheap proxy for the final KHEPRI packet decision.

For every fixed 2-second macro-window:
- research only: build the true KHEPRI 2 s vs 1 s + 1 s oracle labels;
- production candidate: build canonical KMRL FULL256+TAIL16 frontend candidates;
- choose split/keep from the frontend size delta;
- run KHEPRI only for the selected packetization.

The experiment searches only one conservative integer threshold and validates
that threshold-selection procedure leave-one-source-out.
"""
import argparse
import json
import tempfile
import time
from pathlib import Path

import kash02_reset_predictor as k2
import kstream_kmrl_lab as lab

RATE=48_000
CH=2
BITS=16
FB=CH*(BITS//8)
META=64
BLOCK_MS=20
LAYOUT=4
OUT=Path("results/audio/kash05")


def parse_source(value: str):
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source must be name=path")
    name,raw=value.split("=",1)
    if not name or not raw:
        raise argparse.ArgumentTypeError("--source must be name=path")
    return name,Path(raw)


def frontend_size(raw_bytes: bytes, tmp: Path, tag: str):
    raw=tmp/f"{tag}.raw"
    front=tmp/f"{tag}.front"
    raw.write_bytes(raw_bytes)
    t0=time.perf_counter()
    lab.encode_file(raw,front,CH,RATE,BLOCK_MS,LAYOUT)
    elapsed=time.perf_counter()-t0
    return front.stat().st_size,elapsed


def build_rows(name: str, pcm: bytes, cache):
    total=len(pcm)//FB
    rows=[]
    probe_seconds=0.0

    with tempfile.TemporaryDirectory(prefix=f"kash05_{name}_") as td:
        tmp=Path(td)
        for wi,start in enumerate(range(0,total-2*RATE+1,2*RATE)):
            mid=start+RATE
            end=start+2*RATE

            one_a=cache[(start,mid)]
            one_b=cache[(mid,end)]
            two=cache[(start,end)]
            true_join=len(two)+META
            true_split=len(one_a)+META+len(one_b)+META
            true_gain=true_join-true_split

            joined_pcm=pcm[start*FB:end*FB]
            a_pcm=pcm[start*FB:mid*FB]
            b_pcm=pcm[mid*FB:end*FB]

            joined_front,t=frontend_size(joined_pcm,tmp,f"{wi}_joined")
            probe_seconds+=t
            a_front,t=frontend_size(a_pcm,tmp,f"{wi}_a")
            probe_seconds+=t
            b_front,t=frontend_size(b_pcm,tmp,f"{wi}_b")
            probe_seconds+=t

            # Positive proxy gain means split frontends are smaller before
            # KHEPRI. Header/reset overhead is naturally included because the
            # split representation contains two independent frontend streams.
            proxy_gain=joined_front-(a_front+b_front)

            rows.append({
                "source":name,
                "start":start,
                "true_gain_bytes":int(true_gain),
                "frontend_proxy_gain_bytes":int(proxy_gain),
                "joined_frontend_bytes":int(joined_front),
                "split_frontend_bytes":int(a_front+b_front),
            })

    return rows,probe_seconds


def candidate_thresholds(rows):
    vals=sorted(set(r["frontend_proxy_gain_bytes"] for r in rows))
    if not vals:
        return [0]
    out=[vals[0]-1]
    for a,b in zip(vals,vals[1:]):
        out.append((a+b)//2)
    out.append(vals[-1]+1)
    return sorted(set(out))


def evaluate_rows(rows,threshold):
    gains={}
    splits=0
    for r in rows:
        gains.setdefault(r["source"],0)
        if r["frontend_proxy_gain_bytes"]>=threshold:
            gains[r["source"]]+=r["true_gain_bytes"]
            splits+=1
    return gains,splits


def select_threshold(rows):
    sources=sorted({r["source"] for r in rows})
    best={
        "threshold":None,
        "train_gain_bytes":0,
        "train_min_source_gain_bytes":0,
        "train_split_count":0,
        "kind":"never_split",
    }
    best_key=(0,0,0)

    for threshold in candidate_thresholds(rows):
        gains,splits=evaluate_rows(rows,threshold)
        per=[gains.get(s,0) for s in sources]
        if any(x<0 for x in per):
            continue
        total=sum(per)
        if total<=0:
            continue
        key=(total,min(per),-splits)
        if key>best_key:
            best_key=key
            best={
                "threshold":int(threshold),
                "train_gain_bytes":int(total),
                "train_min_source_gain_bytes":int(min(per)),
                "train_split_count":int(splits),
                "kind":"frontend_gain_ge",
            }
    return best


def chosen_segments(src,rule):
    total=src["total"]
    rows_by_start={r["start"]:r for r in src["rows"]}
    out=[]
    split_windows=0
    start=0
    while start<total:
        remaining=total-start
        if remaining<2*RATE:
            out.append((start,remaining))
            break

        row=rows_by_start[start]
        do_split=(
            rule["threshold"] is not None and
            row["frontend_proxy_gain_bytes"]>=rule["threshold"]
        )
        if do_split:
            out.append((start,RATE))
            out.append((start+RATE,RATE))
            split_windows+=1
        else:
            out.append((start,2*RATE))
        start+=2*RATE
    return out,split_windows


def build_source(name,path,exe):
    pcm=path.read_bytes()
    if len(pcm)%FB:
        raise RuntimeError(f"{name}: PCM not frame aligned")
    total=len(pcm)//FB
    cache,positions,oracle_search_s,oracle_n=k2.build_oracle_cache(pcm,exe)
    rows,frontend_probe_s=build_rows(name,pcm,cache)
    return {
        "name":name,
        "pcm":pcm,
        "total":total,
        "cache":cache,
        "positions":positions,
        "rows":rows,
        "oracle_search_seconds":oracle_search_s,
        "oracle_encode_count":oracle_n,
        "frontend_probe_seconds":frontend_probe_s,
    }


def oracle_entries(src):
    total=src["total"]
    cache=src["cache"]
    entries=[]
    full=total//(2*RATE)
    for wi in range(full):
        start=wi*2*RATE
        mid=start+RATE
        end=start+2*RATE
        a=cache[(start,mid)]
        b=cache[(mid,end)]
        two=cache[(start,end)]
        if len(a)+META+len(b)+META < len(two)+META:
            entries.append((start,RATE,a))
            entries.append((mid,RATE,b))
        else:
            entries.append((start,2*RATE,two))
    tail=full*2*RATE
    if tail<total:
        end=total
        entries.append((tail,end-tail,cache[(tail,end)]))
    return entries


def write_variants(src,rule,exe):
    pcm=src["pcm"]
    total=src["total"]
    fixed_segments=k2.fixed_segments(total)
    pred_segments,split_windows=chosen_segments(src,rule)

    fixed_encoded,fixed_encode_s=k2.encode_segments(pcm,fixed_segments,exe)
    pred_encoded,pred_encode_s=k2.encode_segments(pcm,pred_segments,exe)
    oracle=oracle_entries(src)

    source_out=OUT/src["name"]
    source_out.mkdir(parents=True,exist_ok=True)
    old_out=k2.OUT
    k2.OUT=source_out
    try:
        fixed=k2.write_verify("fixed_2s",fixed_encoded,pcm,exe)
        predictor=k2.write_verify("frontend_proxy",pred_encoded,pcm,exe)
        oracle_result=k2.write_verify("oracle_macro",oracle,pcm,exe)
    finally:
        k2.OUT=old_out

    fixed["encode_seconds"]=fixed_encode_s
    predictor["encode_seconds"]=pred_encode_s
    predictor["split_windows"]=split_windows

    return {
        "name":src["name"],
        "fixed":fixed,
        "predictor":predictor,
        "oracle":oracle_result,
        "frontend_probe_seconds":src["frontend_probe_seconds"],
        "oracle_search_seconds":src["oracle_search_seconds"],
        "predictor_gain_bytes":fixed["bytes"]-predictor["bytes"],
        "oracle_gain_bytes":fixed["bytes"]-oracle_result["bytes"],
        "production_candidate_duplicate_khepri_encodes":0,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--source",action="append",type=parse_source,required=True)
    args=ap.parse_args()

    OUT.mkdir(parents=True,exist_ok=True)
    sources=[build_source(name,path,args.kephir) for name,path in args.source]

    folds=[]
    for held in sources:
        train=[
            row
            for src in sources if src["name"]!=held["name"]
            for row in src["rows"]
        ]
        rule=select_threshold(train)
        gains,_=evaluate_rows(held["rows"],rule["threshold"] if rule["threshold"] is not None else 10**18)
        folds.append({
            "held_out":held["name"],
            "rule":rule,
            "held_out_gain_bytes":int(gains.get(held["name"],0)),
        })

    all_rows=[row for src in sources for row in src["rows"]]
    final_rule=select_threshold(all_rows)
    results=[write_variants(src,final_rule,args.kephir) for src in sources]

    fixed_total=sum(x["fixed"]["bytes"] for x in results)
    pred_total=sum(x["predictor"]["bytes"] for x in results)
    oracle_total=sum(x["oracle"]["bytes"] for x in results)
    source_gains=[x["predictor_gain_bytes"] for x in results]
    held_gains=[x["held_out_gain_bytes"] for x in folds]
    proxy_s=sum(x["frontend_probe_seconds"] for x in results)
    oracle_s=sum(x["oracle_search_seconds"] for x in results)

    result={
        "experiment":"KASH-05 canonical frontend-size recovery proxy",
        "final_rule":final_rule,
        "leave_one_source_out":folds,
        "results":results,
        "aggregate":{
            "fixed_bytes":fixed_total,
            "predictor_bytes":pred_total,
            "oracle_bytes":oracle_total,
            "predictor_gain_bytes":fixed_total-pred_total,
            "oracle_gain_bytes":fixed_total-oracle_total,
            "oracle_gain_recovered_percent":(
                100.0*(fixed_total-pred_total)/(fixed_total-oracle_total)
                if fixed_total>oracle_total else 0.0
            ),
            "worst_source_gain_bytes":min(source_gains) if source_gains else 0,
            "worst_heldout_gain_bytes":min(held_gains) if held_gains else 0,
            "frontend_probe_seconds":proxy_s,
            "khepri_oracle_search_seconds":oracle_s,
            "probe_vs_oracle_time_ratio":proxy_s/oracle_s if oracle_s>0 else 0.0,
        },
        "production_candidate_duplicate_khepri_encodes":0,
    }
    result["procedure_promotion_candidate"]=(
        result["aggregate"]["predictor_gain_bytes"]>0
        and result["aggregate"]["worst_source_gain_bytes"]>=0
        and result["aggregate"]["worst_heldout_gain_bytes"]>=0
    )

    (OUT/"KASH05_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KASH05_PASS")
    print("FINAL_RULE",json.dumps(final_rule,sort_keys=True))
    print(
        "AGGREGATE",
        "fixed",fixed_total,
        "predictor",pred_total,
        "oracle",oracle_total,
        "gain",result["aggregate"]["predictor_gain_bytes"],
        "oracle_gain",result["aggregate"]["oracle_gain_bytes"],
        "recovered_pct",f"{result['aggregate']['oracle_gain_recovered_percent']:.3f}",
        "worst_source_gain",result["aggregate"]["worst_source_gain_bytes"],
        "worst_heldout_gain",result["aggregate"]["worst_heldout_gain_bytes"],
        "frontend_probe_s",f"{proxy_s:.6f}",
        "oracle_search_s",f"{oracle_s:.6f}",
        "probe_vs_oracle",f"{result['aggregate']['probe_vs_oracle_time_ratio']:.6f}",
        "procedure_candidate",result["procedure_promotion_candidate"],
    )
    for fold in folds:
        print(
            "LOSO",
            "held_out",fold["held_out"],
            "gain",fold["held_out_gain_bytes"],
            "rule",json.dumps(fold["rule"],sort_keys=True),
        )
    for x in results:
        print(
            "SOURCE",
            x["name"],
            "fixed",x["fixed"]["bytes"],
            "predictor",x["predictor"]["bytes"],
            "oracle",x["oracle"]["bytes"],
            "gain",x["predictor_gain_bytes"],
            "oracle_gain",x["oracle_gain_bytes"],
            "frontend_probe_s",f"{x['frontend_probe_seconds']:.6f}",
        )


if __name__=="__main__":
    main()
