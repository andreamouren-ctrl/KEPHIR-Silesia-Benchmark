#!/usr/bin/env python3
"""
KSV-27 — Numeric feature survey for H3 MOD8 vs ZZ_INTER selection.

Why:
KSV-26 proved symbol entropy cannot distinguish MOD8 from ZZ_INTER because the
mapping is a bijective byte relabeling. KSV-27 therefore measures numeric
features that are not invariant under relabeling and evaluates them with
leave-one-source-out (LOSO) validation.

Research only:
- chroma policy uses the validated H1 selector;
- both MOD8 and ZZ_INTER are encoded to obtain ground-truth final KHEPRI bytes;
- no production selector is promoted here;
- a deterministic byte-cost-optimized decision stump is fitted on all sources
  except one, then evaluated on the held-out source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np

import ksv13_natural_radius_sweep as k13
import ksv17_dense_integer_motion as k17
import ksv20_h3_refinement as k20

OUT=Path("results/video/ksv27_numeric_feature_survey")

def sha_file(path: Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def h1_bits(data: bytes)->float:
    if len(data)<2:
        return float(len(data)*8)
    a=np.frombuffer(data,dtype=np.uint8)
    pair=(a[:-1].astype(np.uint32)<<8)|a[1:].astype(np.uint32)
    counts=np.bincount(pair,minlength=65536).reshape(256,256).astype(np.float64)
    rows=counts.sum(axis=1)
    bits=8.0
    for i in range(256):
        r=rows[i]
        if r<=0:
            continue
        nz=counts[i][counts[i]>0]
        bits += float(np.sum(nz*np.log2(r/nz)))
    return bits

def build_front(chunks,w,h,fpsn,fpsd,gop,chroma,mapping):
    return k17.serialize_dense(chunks,w,h,fpsn,fpsd,gop,chroma,mapping)

def choose_chroma(chunks,w,h,fpsn,fpsd,gop):
    floor_front=build_front(chunks,w,h,fpsn,fpsd,gop,k17.CHROMA_FLOOR,k17.DENSE_MOD8)
    trunc_front=build_front(chunks,w,h,fpsn,fpsd,gop,k17.CHROMA_TRUNC,k17.DENSE_MOD8)
    fh=h1_bits(floor_front)
    th=h1_bits(trunc_front)
    return (k17.CHROMA_FLOOR if fh<=th else k17.CHROMA_TRUNC),fh,th

def residual_bytes(chunks,chroma):
    out=bytearray()
    for _,records in chunks:
        for rec in records:
            if rec[0]!="P":
                continue
            out.extend(rec[2] if chroma==k17.CHROMA_FLOOR else rec[3])
    return bytes(out)

def mapped_zz(data: bytes)->bytes:
    return k17.map_residual(data,k17.ZZ_INTER)

def byte_features(data: bytes,prefix: str):
    a=np.frombuffer(data,dtype=np.uint8)
    if a.size==0:
        return {
            f"{prefix}_mean":0.0,f"{prefix}_std":0.0,
            f"{prefix}_abs_delta":0.0,f"{prefix}_sq_delta":0.0,
            f"{prefix}_low8":0.0,f"{prefix}_low16":0.0,
            f"{prefix}_high240":0.0,f"{prefix}_msb":0.0,
            f"{prefix}_popcount":0.0,
        }
    x=a.astype(np.int16)
    d=np.diff(x).astype(np.int32)
    # Fixed lookup avoids Python loops over millions of bytes.
    pc=np.unpackbits(a[:,None],axis=1).sum(axis=1)
    return {
        f"{prefix}_mean":float(a.mean()),
        f"{prefix}_std":float(a.std()),
        f"{prefix}_abs_delta":float(np.abs(d).mean()) if d.size else 0.0,
        f"{prefix}_sq_delta":float((d.astype(np.float64)**2).mean()) if d.size else 0.0,
        f"{prefix}_low8":float((a<8).mean()),
        f"{prefix}_low16":float((a<16).mean()),
        f"{prefix}_high240":float((a>=240).mean()),
        f"{prefix}_msb":float((a>=128).mean()),
        f"{prefix}_popcount":float(pc.mean()),
    }

def make_features(raw_residual: bytes,chroma:int,stats):
    zz=mapped_zz(raw_residual)
    fm=byte_features(raw_residual,"mod")
    fz=byte_features(zz,"zz")
    f=dict(fm)
    f.update(fz)
    for key in ("mean","std","abs_delta","sq_delta","low8","low16","high240","msb","popcount"):
        f[f"delta_{key}"]=fz[f"zz_{key}"]-fm[f"mod_{key}"]
    # Mapping-invariant source-domain information can still condition the rule.
    a=np.frombuffer(raw_residual,dtype=np.uint8)
    signed=np.where(a<128,a,256-a).astype(np.float64)
    f["signed_mean_mag"]=float(signed.mean()) if signed.size else 0.0
    f["signed_std_mag"]=float(signed.std()) if signed.size else 0.0
    f["chroma_floor"]=1.0 if chroma==k17.CHROMA_FLOOR else 0.0
    f["mean_candidate_evals"]=float(np.mean([s["mean_candidate_evaluations"] for s in stats])) if stats else 0.0
    f["mean_odd_fraction"]=float(np.mean([s["odd_any_fraction"] for s in stats])) if stats else 0.0
    return f

def best_stump(samples):
    """
    Rule form: ZZ if feature <= threshold (or > threshold), else MOD8.
    Objective: minimum final KHEPRI bytes on training samples.
    """
    feature_names=sorted(samples[0]["features"])
    best=None

    def cost_rule(feature,thr,le_is_zz):
        total=0
        for s in samples:
            x=s["features"][feature]
            zz=(x<=thr) if le_is_zz else (x>thr)
            total += s["zz_bytes"] if zz else s["mod_bytes"]
        return total

    # Include constant rules.
    mod_cost=sum(s["mod_bytes"] for s in samples)
    zz_cost=sum(s["zz_bytes"] for s in samples)
    best={"kind":"constant","zz":zz_cost<mod_cost,"train_bytes":min(mod_cost,zz_cost)}

    for feature in feature_names:
        vals=sorted(set(float(s["features"][feature]) for s in samples))
        if len(vals)<2:
            continue
        thresholds=[(a+b)/2.0 for a,b in zip(vals,vals[1:])]
        thresholds=[vals[0]-1e-12,*thresholds,vals[-1]+1e-12]
        for thr in thresholds:
            for le_is_zz in (True,False):
                cost=cost_rule(feature,thr,le_is_zz)
                candidate={
                    "kind":"stump","feature":feature,"threshold":thr,
                    "le_is_zz":le_is_zz,"train_bytes":cost,
                }
                if cost < best["train_bytes"]:
                    best=candidate
    return best

def predict(rule,features):
    if rule["kind"]=="constant":
        return bool(rule["zz"])
    x=features[rule["feature"]]
    return (x<=rule["threshold"]) if rule["le_is_zz"] else (x>rule["threshold"])

def parse_clip(spec):
    p=spec.split(":")
    if len(p)!=6:
        raise argparse.ArgumentTypeError("--clip=name:path:w:h:fps_num:fps_den")
    return {"name":p[0],"path":Path(p[1]).resolve(),"w":int(p[2]),"h":int(p[3]),"fpsn":int(p[4]),"fpsd":int(p[5])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",type=parse_clip,required=True)
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)

    samples=[]
    source_rows=[]

    for clip in args.clip:
        raw=clip["path"].read_bytes()
        fs=k13.frame_size(clip["w"],clip["h"])
        if len(raw)%fs:
            raise RuntimeError("source frame alignment")
        total=len(raw)//fs
        source_samples=[]

        with tempfile.TemporaryDirectory(prefix="ksv27_") as td:
            tmp=Path(td)
            for wi,off in enumerate(range(0,total,20)):
                n=min(20,total-off)
                chunk=raw[off*fs:(off+n)*fs]

                temp,sparse,_=k20.baseline_candidates(
                    chunk,args.kephir,tmp,clip["w"],clip["h"],clip["fpsn"],clip["fpsd"],10,f"w{wi}"
                )
                baseline=k20.choose([temp,*sparse])
                chunks,stats,_=k20.build_h3_records(chunk,clip["w"],clip["h"],10)

                chroma,fh,th=choose_chroma(chunks,clip["w"],clip["h"],clip["fpsn"],clip["fpsd"],10)
                raw_res=residual_bytes(chunks,chroma)
                features=make_features(raw_res,chroma,stats)
                features["chroma_h1_margin"]=abs(fh-th)

                mod_front=build_front(chunks,clip["w"],clip["h"],clip["fpsn"],clip["fpsd"],10,chroma,k17.DENSE_MOD8)
                zz_front=build_front(chunks,clip["w"],clip["h"],clip["fpsn"],clip["fpsd"],10,chroma,k17.DENSE_ZZ)
                mod_payload,_=k13.compress_bytes(mod_front,args.kephir,tmp,f"{clip['name']}.{wi}.mod")
                zz_payload,_=k13.compress_bytes(zz_front,args.kephir,tmp,f"{clip['name']}.{wi}.zz")

                sample={
                    "source":clip["name"],"window":wi,"frames":n,
                    "baseline_bytes":len(baseline["payload"]),
                    "mod_bytes":len(mod_payload),"zz_bytes":len(zz_payload),
                    "oracle_bytes":min(len(mod_payload),len(zz_payload)),
                    "oracle_mapping":"ZZ" if len(zz_payload)<len(mod_payload) else "MOD8",
                    "chroma":"FLOOR" if chroma==k17.CHROMA_FLOOR else "TRUNC",
                    "features":features,
                }
                samples.append(sample)
                source_samples.append(sample)

        source_rows.append({
            "name":clip["name"],
            "windows":len(source_samples),
            "baseline_bytes":sum(s["baseline_bytes"] for s in source_samples),
            "oracle_bytes":sum(s["oracle_bytes"] for s in source_samples),
        })
        print("KSV27_SOURCE_PASS",clip["name"],"windows",len(source_samples),flush=True)

    sources=sorted(set(s["source"] for s in samples))
    predictions=[]
    fold_rules=[]

    for held in sources:
        train=[s for s in samples if s["source"]!=held]
        test=[s for s in samples if s["source"]==held]
        rule=best_stump(train)
        fold_rules.append({"held_out":held,**rule})
        for s in test:
            zz=predict(rule,s["features"])
            selected=s["zz_bytes"] if zz else s["mod_bytes"]
            predictions.append({
                "source":s["source"],"window":s["window"],
                "selected_mapping":"ZZ" if zz else "MOD8",
                "oracle_mapping":s["oracle_mapping"],
                "selected_bytes":selected,
                "oracle_bytes":s["oracle_bytes"],
                "baseline_bytes":s["baseline_bytes"],
                "match":("ZZ" if zz else "MOD8")==s["oracle_mapping"],
                "rule":rule,
            })

    baseline=sum(p["baseline_bytes"] for p in predictions)
    selected=sum(p["selected_bytes"] for p in predictions)
    oracle=sum(p["oracle_bytes"] for p in predictions)
    oracle_gain=baseline-oracle
    selected_gain=baseline-selected
    recovered=100.0*selected_gain/oracle_gain if oracle_gain>0 else 100.0
    penalty=100.0*(selected/oracle-1.0)
    matches=sum(p["match"] for p in predictions)

    # Fit-all rule is diagnostic only; LOSO is the decision metric.
    fit_all=best_stump(samples)

    result={
        "experiment":"KSV-27 numeric feature survey",
        "sample_count":len(samples),
        "source_count":len(sources),
        "samples":samples,
        "loso":{
            "baseline_bytes":baseline,
            "selected_bytes":selected,
            "oracle_bytes":oracle,
            "gain_recovered_percent":recovered,
            "delta_vs_oracle_percent":penalty,
            "mode_matches":matches,
            "window_count":len(predictions),
            "predictions":predictions,
            "fold_rules":fold_rules,
        },
        "fit_all_rule":fit_all,
        "notes":[
            "No selector is promoted by this experiment.",
            "LOSO folds hold out every window from one source at a time.",
            "Rule fitting minimizes final KHEPRI byte cost, not classification error.",
            "Features are numeric/non-invariant under MOD8<->ZZ relabeling.",
        ],
    }
    (OUT/"KSV27_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KSV27_NUMERIC_FEATURE_SURVEY_PASS")
    print(
        "KSV27_LOSO",
        "baseline",baseline,
        "selected",selected,
        "oracle",oracle,
        "recovered_pct",f"{recovered:.3f}",
        "delta_oracle_pct",f"{penalty:.6f}",
        "matches",matches,
        "windows",len(predictions),
    )
    print("KSV27_FIT_ALL_RULE",json.dumps(fit_all,sort_keys=True))
    for r in fold_rules:
        print("KSV27_FOLD_RULE",json.dumps(r,sort_keys=True))

if __name__=="__main__":
    main()
