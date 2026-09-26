#!/usr/bin/env python3
"""
EXP-105 — Quarter Distribution Drift Study

Tests whether cheap byte-distribution drift between 128 KiB quarters explains
the grain-oracle decisions that entropy spread misses.

No production policy change. Exact grain sizes are measured only for the
target coarse buckets, then correlated with:
- maximum pairwise total-variation distance between quarter histograms;
- mean total-variation distance from the parent histogram;
- quarter printable/zero fraction ranges.
"""
from pathlib import Path
import collections
import json
import math
import shutil
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
sys.path.insert(0,str(ROOT/"research"/"packaging"))
import kephir_final as K
import router_matrix_v2 as RM

E=K.E
CH=512*1024
Q=128*1024
TARGETS={
    "l2:h7:z0:p1:s0",
    "l2:h5:z2:p1:s6",
    "l2:h5:z1:p3:s2",
}


def histogram(buf):
    counts=[0]*256
    for b in buf:
        counts[b]+=1
    n=max(1,len(buf))
    return [c/n for c in counts]


def tv(a,b):
    return 0.5*sum(abs(x-y) for x,y in zip(a,b))


def distribution_features(parent):
    quarters=[
        parent[i:i+Q]
        for i in range(0,len(parent),Q)
        if parent[i:i+Q]
    ]
    hists=[histogram(q) for q in quarters]
    global_hist=histogram(parent)

    pairwise=[
        tv(hists[i],hists[j])
        for i in range(len(hists))
        for j in range(i+1,len(hists))
    ]
    global_tvs=[tv(h,global_hist) for h in hists]

    printable=[]
    zero=[]
    for q in quarters:
        n=max(1,len(q))
        printable.append(sum(
            1 for b in q
            if b in (9,10,13) or 32<=b<127
        )/n)
        zero.append(q.count(0)/n)

    # Quarter-by-quarter byte mean catches broad distribution shifts cheaply.
    means=[
        sum(q)/max(1,len(q))
        for q in quarters
    ]

    return {
        "tv_max":max(pairwise) if pairwise else 0.0,
        "tv_mean_pair":sum(pairwise)/len(pairwise) if pairwise else 0.0,
        "tv_mean_global":sum(global_tvs)/len(global_tvs) if global_tvs else 0.0,
        "printable_range":max(printable)-min(printable) if printable else 0.0,
        "zero_range":max(zero)-min(zero) if zero else 0.0,
        "byte_mean_range":max(means)-min(means) if means else 0.0,
    }


def exact_sizes(parent,tmp,tag):
    tag="".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tag)
    candidates=[128*1024,256*1024,len(parent)]
    out={}
    for g in sorted(set(g for g in candidates if g<=len(parent))):
        out[g]=E.measure_grain_exact(
            parent,g,tmp,0,f"{tag}_g{g}"
        )
    return out


def iter_files(root):
    root=Path(root)
    if root.is_file():
        yield root
    else:
        yield from (
            p for p in sorted(root.rglob("*"))
            if p.is_file() and not p.is_symlink()
        )


def audit_file(path,label,tmp,rows):
    raw=path.read_bytes()
    for pidx,start in enumerate(range(0,len(raw),CH)):
        parent=raw[start:start+CH]
        if len(parent)!=CH:
            continue
        coarse=E.grain_feature_bucket(parent)
        if coarse not in TARGETS:
            continue
        sizes=exact_sizes(parent,tmp,f"{label}_{pidx}")
        best=min(sizes,key=lambda g:(sizes[g],g))
        feat=distribution_features(parent)
        row={
            "dataset":label,
            "parent_index":pidx,
            "coarse":coarse,
            "best_grain":best,
            "sizes":{str(k):v for k,v in sizes.items()},
            "gain_vs_512":sizes[512*1024]-sizes[best],
            **feat,
        }
        rows.append(row)
        print("EXP105_PARENT",json.dumps(row,sort_keys=True),flush=True)


def main():
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp105_distribution_drift"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()
    tmp=work/"tmp"; tmp.mkdir()

    rows=[]
    for p in sorted(corpus.iterdir()):
        if p.is_file():
            audit_file(p,"silesia/"+p.name,tmp,rows)

    datasets=RM.materialize_matrix(work/"matrix",corpus)
    for name,root in datasets.items():
        if name=="silesia":
            continue
        for p in iter_files(root):
            rel=p.relative_to(root)
            audit_file(
                p,
                f"matrix/{name}/{rel.as_posix()}",
                tmp,
                rows
            )

    summary={}
    for coarse in sorted(TARGETS):
        subset=[r for r in rows if r["coarse"]==coarse]
        by_best={}
        for r in subset:
            a=by_best.setdefault(str(r["best_grain"]),{
                "count":0,
                "gain_vs_512":0,
                "tv_max_min":None,
                "tv_max_max":None,
                "tv_mean_global_min":None,
                "tv_mean_global_max":None,
            })
            a["count"]+=1
            a["gain_vs_512"]+=r["gain_vs_512"]
            for key in ("tv_max","tv_mean_global"):
                mn=key+"_min"; mx=key+"_max"
                a[mn]=r[key] if a[mn] is None else min(a[mn],r[key])
                a[mx]=r[key] if a[mx] is None else max(a[mx],r[key])
        summary[coarse]=by_best
        print(
            "EXP105_COARSE",coarse,
            json.dumps(by_best,sort_keys=True),
            flush=True
        )

    result={
        "experiment":"EXP-105",
        "rows":rows,
        "summary":summary,
    }
    Path("exp105_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )
    print("EXP105_STUDY_COMPLETE",flush=True)


if __name__=="__main__":
    main()
