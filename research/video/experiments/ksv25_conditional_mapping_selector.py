#!/usr/bin/env python3
"""
KSV-25 — H3 residual-mapping selector.

KSV-22 established that its cheap entropy selector chose the oracle FLOOR/TRUNC
chroma policy on all 15 Natural Video Corpus windows. Every miss was only
MOD8 versus ZZ_INTER.

KSV-25 therefore separates the decisions:
1. choose FLOOR/TRUNC using the same cheap first-order frontend entropy signal;
2. on the selected chroma residual, choose ZZ_INTER when mean signed residual
   magnitude < 2.60, otherwise MOD8;
3. perform one KHEPRI encode in the production-candidate path.

Research mode also encodes all four H3 candidates to measure the oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

import ksv13_natural_radius_sweep as k13
import ksv17_dense_integer_motion as k17
import ksv20_h3_refinement as k20

OUT=Path("results/video/ksv25_conditional_mapping_selector")
THRESHOLD=2.60

CONFIGS=(
    (k17.CHROMA_FLOOR,k17.DENSE_MOD8,"H3_FLOOR_MOD8",k20.MODE_H3_FLOOR_MOD8),
    (k17.CHROMA_FLOOR,k17.DENSE_ZZ,"H3_FLOOR_ZZ",k20.MODE_H3_FLOOR_ZZ),
    (k17.CHROMA_TRUNC,k17.DENSE_MOD8,"H3_TRUNC_MOD8",k20.MODE_H3_TRUNC_MOD8),
    (k17.CHROMA_TRUNC,k17.DENSE_ZZ,"H3_TRUNC_ZZ",k20.MODE_H3_TRUNC_ZZ),
)

MODE_BY_POLICY={
    (k17.CHROMA_FLOOR,k17.DENSE_MOD8):("H3_FLOOR_MOD8",k20.MODE_H3_FLOOR_MOD8),
    (k17.CHROMA_FLOOR,k17.DENSE_ZZ):("H3_FLOOR_ZZ",k20.MODE_H3_FLOOR_ZZ),
    (k17.CHROMA_TRUNC,k17.DENSE_MOD8):("H3_TRUNC_MOD8",k20.MODE_H3_TRUNC_MOD8),
    (k17.CHROMA_TRUNC,k17.DENSE_ZZ):("H3_TRUNC_ZZ",k20.MODE_H3_TRUNC_ZZ),
}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def h1_bits(data: bytes) -> float:
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


def signed_mag_bytes(data: bytes) -> tuple[int,int]:
    a=np.frombuffer(data,dtype=np.uint8)
    if a.size==0:
        return 0,0
    signed=np.where(a<128,a,256-a).astype(np.uint64)
    return int(signed.sum()),int(a.size)


def residual_mean_magnitude(chunks,chroma_policy: int) -> float:
    total=0
    count=0
    for _,records in chunks:
        for rec in records:
            if rec[0]!="P":
                continue
            residual=rec[2] if chroma_policy==k17.CHROMA_FLOOR else rec[3]
            s,n=signed_mag_bytes(residual)
            total+=s
            count+=n
    return total/count if count else 0.0


def build_front(chunks,w,h,fpsn,fpsd,gop,chroma,mapping):
    return k17.serialize_dense(
        chunks,w,h,fpsn,fpsd,gop,chroma,mapping
    )


def choose_chroma(chunks,w,h,fpsn,fpsd,gop):
    # KSV-22 H1 always selected a MOD8 frontend and matched oracle chroma 15/15.
    floor_front=build_front(
        chunks,w,h,fpsn,fpsd,gop,k17.CHROMA_FLOOR,k17.DENSE_MOD8
    )
    trunc_front=build_front(
        chunks,w,h,fpsn,fpsd,gop,k17.CHROMA_TRUNC,k17.DENSE_MOD8
    )
    floor_h1=h1_bits(floor_front)
    trunc_h1=h1_bits(trunc_front)
    if floor_h1<=trunc_h1:
        return k17.CHROMA_FLOOR,floor_h1,trunc_h1
    return k17.CHROMA_TRUNC,floor_h1,trunc_h1


def build_window(chunk,exe,tmp,w,h,fpsn,fpsd,gop,tag):
    temp,sparse,sparse_search_s=k20.baseline_candidates(
        chunk,exe,tmp,w,h,fpsn,fpsd,gop,tag
    )
    baseline=k20.choose([temp,*sparse])

    chunks,stats,h3_search_s=k20.build_h3_records(chunk,w,h,gop)

    chroma,floor_h1,trunc_h1=choose_chroma(
        chunks,w,h,fpsn,fpsd,gop
    )
    mean_mag=residual_mean_magnitude(chunks,chroma)
    # KSV-24 showed every remaining miss occurred when the chroma
    # selector chose FLOOR: the oracle wanted ZZ_INTER on all such windows.
    # TRUNC windows still follow the historical mean-magnitude split.
    mapping=(
        k17.DENSE_ZZ
        if chroma==k17.CHROMA_FLOOR
        else (k17.DENSE_ZZ if mean_mag<THRESHOLD else k17.DENSE_MOD8)
    )
    selected_label,selected_mode=MODE_BY_POLICY[(chroma,mapping)]
    selected_front=build_front(
        chunks,w,h,fpsn,fpsd,gop,chroma,mapping
    )
    selected_payload,selected_backend_s=k13.compress_bytes(
        selected_front,exe,tmp,f"{tag}.selected"
    )

    # Research oracle: all candidates are encoded only for measurement.
    rows=[]
    for cpol,rmode,label,mode in CONFIGS:
        if cpol==chroma and rmode==mapping:
            payload=selected_payload
            backend_s=selected_backend_s
            front=selected_front
        else:
            front=build_front(
                chunks,w,h,fpsn,fpsd,gop,cpol,rmode
            )
            payload,backend_s=k13.compress_bytes(
                front,exe,tmp,f"{tag}.{label.lower()}"
            )
        rows.append({
            "chroma":cpol,
            "mapping":rmode,
            "label":label,
            "mode":mode,
            "payload":payload,
            "bytes":len(payload),
            "backend_seconds":backend_s,
        })

    oracle=min(rows,key=lambda r:(r["bytes"],r["mode"]))
    selected=next(
        r for r in rows
        if r["chroma"]==chroma and r["mapping"]==mapping
    )

    mean_evals=(
        sum(s["mean_candidate_evaluations"] for s in stats)/len(stats)
        if stats else 0.0
    )
    mean_odd=(
        sum(s["odd_any_fraction"] for s in stats)/len(stats)
        if stats else 0.0
    )

    return {
        "baseline":baseline,
        "selected":selected,
        "oracle":oracle,
        "mean_mag":mean_mag,
        "floor_h1":floor_h1,
        "trunc_h1":trunc_h1,
        "chroma_match":selected["chroma"]==oracle["chroma"],
        "mapping_match":selected["mapping"]==oracle["mapping"],
        "mode_match":selected["label"]==oracle["label"],
        "h3_search_seconds":h3_search_s,
        "baseline_search_seconds":sparse_search_s,
        "mean_evals":mean_evals,
        "mean_odd":mean_odd,
        "research_all_backend_seconds":sum(r["backend_seconds"] for r in rows),
        "selected_backend_seconds":selected_backend_s,
    }


def encode_source(src,prefix,exe,w,h,fpsn,fpsd,gop=10,route_span=20):
    raw=src.read_bytes()
    fs=k13.frame_size(w,h)
    if len(raw)%fs:
        raise RuntimeError("source frame alignment")
    total=len(raw)//fs

    selected_entries=[]
    oracle_entries=[]
    windows=[]
    baseline_bytes=0
    h3_search_seconds=0.0
    selected_backend_seconds=0.0
    research_all_backend_seconds=0.0

    with tempfile.TemporaryDirectory(prefix="ksv25_") as td:
        tmp=Path(td)
        for wi,off in enumerate(range(0,total,route_span)):
            n=min(route_span,total-off)
            chunk=raw[off*fs:(off+n)*fs]
            r=build_window(
                chunk,exe,tmp,w,h,fpsn,fpsd,gop,f"w{wi}"
            )
            baseline_bytes+=len(r["baseline"]["payload"])
            h3_search_seconds+=r["h3_search_seconds"]
            selected_backend_seconds+=r["selected_backend_seconds"]
            research_all_backend_seconds+=r["research_all_backend_seconds"]

            for target,key in (
                (selected_entries,"selected"),
                (oracle_entries,"oracle"),
            ):
                e=dict(r[key])
                e["frames"]=n
                target.append(e)

            windows.append({
                "window":wi,
                "frames":n,
                "baseline_bytes":len(r["baseline"]["payload"]),
                "selected":r["selected"]["label"],
                "selected_bytes":r["selected"]["bytes"],
                "oracle":r["oracle"]["label"],
                "oracle_bytes":r["oracle"]["bytes"],
                "mean_signed_magnitude":r["mean_mag"],
                "floor_h1_bits":r["floor_h1"],
                "trunc_h1_bits":r["trunc_h1"],
                "chroma_match":r["chroma_match"],
                "mapping_match":r["mapping_match"],
                "mode_match":r["mode_match"],
                "mean_evals":r["mean_evals"],
                "mean_odd":r["mean_odd"],
            })

    paths={
        "selected":prefix.with_suffix(".selected.k24"),
        "oracle":prefix.with_suffix(".oracle.k24"),
    }
    k20.write_outer(
        paths["selected"],w,h,fpsn,fpsd,gop,route_span,selected_entries
    )
    k20.write_outer(
        paths["oracle"],w,h,fpsn,fpsd,gop,route_span,oracle_entries
    )

    baseline_bytes += k20.OUTER_HDR.size + len(windows)*k20.OUTER_ENT.size

    return {
        "paths":paths,
        "baseline_bytes":baseline_bytes,
        "selected":{
            "bytes":paths["selected"].stat().st_size,
            "modes":dict(sorted(Counter(e["label"] for e in selected_entries).items())),
            "selected_backend_seconds":selected_backend_seconds,
        },
        "oracle":{
            "bytes":paths["oracle"].stat().st_size,
            "modes":dict(sorted(Counter(e["label"] for e in oracle_entries).items())),
            "research_all_backend_seconds":research_all_backend_seconds,
        },
        "h3_search_seconds":h3_search_seconds,
        "windows":windows,
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
        for policy in ("selected","oracle"):
            dst=OUT/f"{clip['name']}.{policy}.decoded.yuv"
            t0=time.perf_counter()
            k20.decode_outer(enc["paths"][policy],dst,args.kephir)
            seconds=time.perf_counter()-t0
            ok=sha_file(dst)==sha_file(clip["path"])
            if not ok:
                raise RuntimeError(f"{clip['name']} {policy}: SHA mismatch")
            decoded[policy]={"decode_seconds":seconds,"sha_ok":True}

        row={
            "name":clip["name"],
            "raw_bytes":clip["path"].stat().st_size,
            "baseline_bytes":enc["baseline_bytes"],
            "selected":{**enc["selected"],**decoded["selected"]},
            "oracle":{**enc["oracle"],**decoded["oracle"]},
            "h3_search_seconds":enc["h3_search_seconds"],
            "windows":enc["windows"],
        }

        oracle_gain=row["baseline_bytes"]-row["oracle"]["bytes"]
        selected_gain=row["baseline_bytes"]-row["selected"]["bytes"]
        row["selected"]["gain_recovered_percent"]=(
            100.0*selected_gain/oracle_gain if oracle_gain>0 else 0.0
        )
        row["selected"]["delta_vs_oracle_percent"]=(
            100.0*(row["selected"]["bytes"]/row["oracle"]["bytes"]-1.0)
        )

        rows.append(row)
        print(
            "KSV25_SOURCE_PASS",clip["name"],
            "baseline",row["baseline_bytes"],
            "selected",row["selected"]["bytes"],
            "oracle",row["oracle"]["bytes"],
            "recovered",f'{row["selected"]["gain_recovered_percent"]:.3f}',
            flush=True,
        )

    baseline=sum(r["baseline_bytes"] for r in rows)
    selected=sum(r["selected"]["bytes"] for r in rows)
    oracle=sum(r["oracle"]["bytes"] for r in rows)
    oracle_gain=baseline-oracle
    selected_gain=baseline-selected

    windows=[w for r in rows for w in r["windows"]]
    aggregate={
        "baseline_bytes":baseline,
        "selected_bytes":selected,
        "oracle_bytes":oracle,
        "gain_recovered_percent":(
            100.0*selected_gain/oracle_gain if oracle_gain>0 else 0.0
        ),
        "delta_vs_oracle_percent":100.0*(selected/oracle-1.0),
        "window_count":len(windows),
        "mode_match_windows":sum(w["mode_match"] for w in windows),
        "chroma_match_windows":sum(w["chroma_match"] for w in windows),
        "mapping_match_windows":sum(w["mapping_match"] for w in windows),
        "h3_search_seconds":sum(r["h3_search_seconds"] for r in rows),
        "selected_backend_seconds":sum(
            r["selected"]["selected_backend_seconds"] for r in rows
        ),
        "research_all_backend_seconds":sum(
            r["oracle"]["research_all_backend_seconds"] for r in rows
        ),
    }

    result={
        "experiment":"KSV-25 H3 residual mapping selector",
        "mapping_threshold":THRESHOLD,
        "mapping_rule":"FLOOR -> ZZ_INTER; TRUNC -> ZZ_INTER if mean_signed_residual_magnitude < threshold else MOD8",
        "chroma_rule":"first-order entropy over FLOOR/TRUNC MOD8 H3 frontend",
        "production_candidate_duplicate_khepri_encodes":0,
        "rows":rows,
        "aggregate":aggregate,
    }
    (OUT/"KSV25_RESULTS.json").write_text(json.dumps(result,indent=2))

    print("KSV25_RESIDUAL_MAPPING_SELECTOR_PASS")
    print(
        "KSV25_AGGREGATE",
        "baseline",baseline,
        "selected",selected,
        "oracle",oracle,
        "recovered_pct",f'{aggregate["gain_recovered_percent"]:.3f}',
        "delta_oracle_pct",f'{aggregate["delta_vs_oracle_percent"]:.6f}',
        "mode_matches",aggregate["mode_match_windows"],
        "chroma_matches",aggregate["chroma_match_windows"],
        "mapping_matches",aggregate["mapping_match_windows"],
        "windows",aggregate["window_count"],
    )
    for r in rows:
        for w in r["windows"]:
            print(
                "WINDOW",r["name"],w["window"],
                "mean_mag",f'{w["mean_signed_magnitude"]:.6f}',
                "selected",w["selected"],
                "oracle",w["oracle"],
                "mapping_match",int(w["mapping_match"]),
            )


if __name__=="__main__":
    main()
