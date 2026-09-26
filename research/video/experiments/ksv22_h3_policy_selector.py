#!/usr/bin/env python3
"""
KSV-22 — H3 production policy selector.

Goal:
choose FLOOR/TRUNC chroma rounding and MOD8/ZZ residual mapping before KHEPRI,
using cheap entropy estimators and a single H3 motion search.

Research mode still compresses all four H3 candidates to measure the oracle.
The production-candidate path selects one frontend first, then would perform
exactly one KHEPRI encode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

import ksv13_natural_radius_sweep as k13
import ksv17_dense_integer_motion as k17
import ksv20_h3_refinement as k20

OUT=Path("results/video/ksv22_h3_policy_selector")

CONFIGS=(
    (k17.CHROMA_FLOOR,k17.DENSE_MOD8,"H3_FLOOR_MOD8",k20.MODE_H3_FLOOR_MOD8),
    (k17.CHROMA_FLOOR,k17.DENSE_ZZ,"H3_FLOOR_ZZ",k20.MODE_H3_FLOOR_ZZ),
    (k17.CHROMA_TRUNC,k17.DENSE_MOD8,"H3_TRUNC_MOD8",k20.MODE_H3_TRUNC_MOD8),
    (k17.CHROMA_TRUNC,k17.DENSE_ZZ,"H3_TRUNC_ZZ",k20.MODE_H3_TRUNC_ZZ),
)


def h0_bits(data: bytes) -> float:
    if not data:
        return 0.0
    a=np.frombuffer(data,dtype=np.uint8)
    counts=np.bincount(a,minlength=256).astype(np.float64)
    nz=counts[counts>0]
    n=float(len(a))
    return float(np.sum(nz*np.log2(n/nz)))


def h1_bits(data: bytes) -> float:
    if len(data)<2:
        return h0_bits(data)
    a=np.frombuffer(data,dtype=np.uint8)
    pair=(a[:-1].astype(np.uint32)<<8)|a[1:].astype(np.uint32)
    counts=np.bincount(pair,minlength=65536).reshape(256,256).astype(np.float64)
    rows=counts.sum(axis=1)
    bits=0.0
    for i in range(256):
        r=rows[i]
        if r<=0:
            continue
        nz=counts[i][counts[i]>0]
        bits += float(np.sum(nz*np.log2(r/nz)))
    # First byte modeled with a zero-order cost.
    return bits + 8.0


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_metric(rows, key):
    return min(rows,key=lambda r:(r[key],r["mode"]))


def build_window(chunk,exe,tmp,w,h,fpsn,fpsd,gop,tag):
    # Baseline is research-only here and is used solely to quantify how much of
    # the H3 gain the cheap selector preserves.
    temp,sparse,sparse_search_s=k20.baseline_candidates(
        chunk,exe,tmp,w,h,fpsn,fpsd,gop,tag
    )
    baseline=k20.choose([temp,*sparse])

    chunks,stats,h3_search_s=k20.build_h3_records(chunk,w,h,gop)
    mean_evals=(
        sum(s["mean_candidate_evaluations"] for s in stats)/len(stats)
        if stats else 0.0
    )
    mean_odd=(
        sum(s["odd_any_fraction"] for s in stats)/len(stats)
        if stats else 0.0
    )

    rows=[]
    decision_t0=time.perf_counter()
    for chroma,residual_mode,label,mode in CONFIGS:
        front=k17.serialize_dense(
            chunks,w,h,fpsn,fpsd,gop,chroma,residual_mode
        )
        rows.append({
            "label":label,
            "mode":mode,
            "front":front,
            "h0_bits":h0_bits(front),
            "h1_bits":h1_bits(front),
        })
    decision_seconds=time.perf_counter()-decision_t0

    h0_pick=choose_metric(rows,"h0_bits")
    h1_pick=choose_metric(rows,"h1_bits")

    # Research oracle only: encode all four candidates after the decisions have
    # already been made. Production would encode only its selected candidate.
    for row in rows:
        payload,backend_s=k13.compress_bytes(
            row["front"],exe,tmp,f"{tag}.{row['label'].lower()}"
        )
        row["payload"]=payload
        row["bytes"]=len(payload)
        row["backend_seconds"]=backend_s

    oracle=min(rows,key=lambda r:(r["bytes"],r["mode"]))

    return {
        "baseline":baseline,
        "rows":rows,
        "h0_pick":h0_pick,
        "h1_pick":h1_pick,
        "oracle":oracle,
        "decision_seconds":decision_seconds,
        "h3_search_seconds":h3_search_s,
        "baseline_search_seconds":sparse_search_s,
        "mean_evals":mean_evals,
        "mean_odd":mean_odd,
    }


def encode_source(src,prefix,exe,w,h,fpsn,fpsd,gop=10,route_span=20):
    raw=src.read_bytes()
    fs=k13.frame_size(w,h)
    if len(raw)%fs:
        raise RuntimeError("source frame alignment")
    total=len(raw)//fs

    entries={"h0":[],"h1":[],"oracle":[]}
    summary=[]
    baseline_bytes=0
    decision_seconds=0.0
    selected_backend_seconds={"h0":0.0,"h1":0.0}
    oracle_backend_seconds=0.0
    h3_search_seconds=0.0

    with tempfile.TemporaryDirectory(prefix="ksv22_") as td:
        tmp=Path(td)
        for wi,off in enumerate(range(0,total,route_span)):
            n=min(route_span,total-off)
            chunk=raw[off*fs:(off+n)*fs]
            r=build_window(
                chunk,exe,tmp,w,h,fpsn,fpsd,gop,f"w{wi}"
            )

            baseline_bytes+=len(r["baseline"]["payload"])
            decision_seconds+=r["decision_seconds"]
            h3_search_seconds+=r["h3_search_seconds"]
            oracle_backend_seconds+=sum(x["backend_seconds"] for x in r["rows"])

            for policy,pick in (
                ("h0",r["h0_pick"]),
                ("h1",r["h1_pick"]),
                ("oracle",r["oracle"]),
            ):
                e=dict(pick)
                e["frames"]=n
                entries[policy].append(e)

            selected_backend_seconds["h0"]+=r["h0_pick"]["backend_seconds"]
            selected_backend_seconds["h1"]+=r["h1_pick"]["backend_seconds"]

            summary.append({
                "window":wi,
                "frames":n,
                "baseline_bytes":len(r["baseline"]["payload"]),
                "h0_selected":r["h0_pick"]["label"],
                "h0_bytes":r["h0_pick"]["bytes"],
                "h1_selected":r["h1_pick"]["label"],
                "h1_bytes":r["h1_pick"]["bytes"],
                "oracle_selected":r["oracle"]["label"],
                "oracle_bytes":r["oracle"]["bytes"],
                "h0_match":r["h0_pick"]["label"]==r["oracle"]["label"],
                "h1_match":r["h1_pick"]["label"]==r["oracle"]["label"],
                "mean_evals":r["mean_evals"],
                "mean_odd":r["mean_odd"],
            })

    paths={}
    for policy in ("h0","h1","oracle"):
        path=prefix.with_suffix(f".{policy}.k20")
        k20.write_outer(path,w,h,fpsn,fpsd,gop,route_span,entries[policy])
        paths[policy]=path

    return {
        "paths":paths,
        "baseline_bytes":baseline_bytes,
        "h0":{
            "bytes":paths["h0"].stat().st_size,
            "modes":dict(sorted(Counter(e["label"] for e in entries["h0"]).items())),
            "selected_backend_seconds":selected_backend_seconds["h0"],
        },
        "h1":{
            "bytes":paths["h1"].stat().st_size,
            "modes":dict(sorted(Counter(e["label"] for e in entries["h1"]).items())),
            "selected_backend_seconds":selected_backend_seconds["h1"],
        },
        "oracle":{
            "bytes":paths["oracle"].stat().st_size,
            "modes":dict(sorted(Counter(e["label"] for e in entries["oracle"]).items())),
            "research_all_candidate_backend_seconds":oracle_backend_seconds,
        },
        "decision_seconds":decision_seconds,
        "h3_search_seconds":h3_search_seconds,
        "windows":summary,
    }


def parse_clip(spec):
    p=spec.split(":")
    if len(p)!=6:
        raise argparse.ArgumentTypeError(
            "--clip=name:path:w:h:fps_num:fps_den"
        )
    return {
        "name":p[0],"path":Path(p[1]).resolve(),
        "w":int(p[2]),"h":int(p[3]),
        "fpsn":int(p[4]),"fpsd":int(p[5]),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",type=parse_clip,required=True)
    args=ap.parse_args()

    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]

    for clip in args.clip:
        enc=encode_source(
            clip["path"],OUT/clip["name"],args.kephir,
            clip["w"],clip["h"],clip["fpsn"],clip["fpsd"]
        )

        decoded={}
        for policy in ("h0","h1","oracle"):
            dst=OUT/f"{clip['name']}.{policy}.decoded.yuv"
            t0=time.perf_counter()
            k20.decode_outer(enc["paths"][policy],dst,args.kephir)
            dec_s=time.perf_counter()-t0
            ok=sha_file(dst)==sha_file(clip["path"])
            if not ok:
                raise RuntimeError(f"{clip['name']} {policy}: SHA mismatch")
            decoded[policy]={"decode_seconds":dec_s,"sha_ok":True}

        row={
            "name":clip["name"],
            "raw_bytes":clip["path"].stat().st_size,
            "baseline_bytes":enc["baseline_bytes"],
            "h0":{**enc["h0"],**decoded["h0"]},
            "h1":{**enc["h1"],**decoded["h1"]},
            "oracle":{**enc["oracle"],**decoded["oracle"]},
            "decision_seconds":enc["decision_seconds"],
            "h3_search_seconds":enc["h3_search_seconds"],
            "windows":enc["windows"],
        }

        oracle_gain=row["baseline_bytes"]-row["oracle"]["bytes"]
        for policy in ("h0","h1"):
            gain=row["baseline_bytes"]-row[policy]["bytes"]
            row[policy]["gain_recovered_percent"]=(
                100.0*gain/oracle_gain if oracle_gain>0 else 0.0
            )
            row[policy]["delta_vs_oracle_percent"]=(
                100.0*(row[policy]["bytes"]/row["oracle"]["bytes"]-1.0)
            )

        rows.append(row)
        print(
            "KSV22_SOURCE_PASS",clip["name"],
            "baseline",row["baseline_bytes"],
            "h0",row["h0"]["bytes"],
            "h1",row["h1"]["bytes"],
            "oracle",row["oracle"]["bytes"],
            "h0_recovered",f'{row["h0"]["gain_recovered_percent"]:.3f}',
            "h1_recovered",f'{row["h1"]["gain_recovered_percent"]:.3f}',
            flush=True,
        )

    agg={}
    baseline=sum(r["baseline_bytes"] for r in rows)
    oracle=sum(r["oracle"]["bytes"] for r in rows)
    oracle_gain=baseline-oracle
    agg["baseline_bytes"]=baseline
    agg["oracle_bytes"]=oracle

    for policy in ("h0","h1"):
        b=sum(r[policy]["bytes"] for r in rows)
        gain=baseline-b
        agg[policy]={
            "bytes":b,
            "gain_recovered_percent":(
                100.0*gain/oracle_gain if oracle_gain>0 else 0.0
            ),
            "delta_vs_oracle_percent":100.0*(b/oracle-1.0),
            "oracle_mode_match_windows":sum(
                1 for r in rows for w in r["windows"]
                if w[f"{policy}_match"]
            ),
            "window_count":sum(len(r["windows"]) for r in rows),
            "selected_backend_seconds":sum(
                r[policy]["selected_backend_seconds"] for r in rows
            ),
        }

    agg["decision_seconds"]=sum(r["decision_seconds"] for r in rows)
    agg["h3_search_seconds"]=sum(r["h3_search_seconds"] for r in rows)
    agg["research_all_candidate_backend_seconds"]=sum(
        r["oracle"]["research_all_candidate_backend_seconds"] for r in rows
    )

    result={
        "experiment":"KSV-22 H3 production policy selector",
        "estimators":{
            "h0":"zero-order byte entropy of serialized H3 frontend",
            "h1":"first-order conditional byte entropy of serialized H3 frontend",
        },
        "rows":rows,
        "aggregate":agg,
        "production_candidate_duplicate_khepri_encodes":0,
        "notes":[
            "Research encodes all four H3 candidates only to measure oracle quality.",
            "Production candidate selects frontend before KHEPRI and encodes one candidate.",
            "FLOOR/TRUNC share the same H3 luma motion decisions.",
        ],
    }
    (OUT/"KSV22_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KSV22_H3_POLICY_SELECTOR_PASS")
    print(
        "KSV22_AGGREGATE",
        "baseline",baseline,
        "h0",agg["h0"]["bytes"],
        "h1",agg["h1"]["bytes"],
        "oracle",oracle,
        "h0_recovered",f'{agg["h0"]["gain_recovered_percent"]:.3f}',
        "h1_recovered",f'{agg["h1"]["gain_recovered_percent"]:.3f}',
        "h0_matches",agg["h0"]["oracle_mode_match_windows"],
        "h1_matches",agg["h1"]["oracle_mode_match_windows"],
        "windows",agg["h1"]["window_count"],
        "decision_seconds",f'{agg["decision_seconds"]:.6f}',
    )


if __name__=="__main__":
    main()
