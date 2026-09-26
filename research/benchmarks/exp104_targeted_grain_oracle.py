#!/usr/bin/env python3
"""
EXP-104 — Targeted Grain Oracle

Audits only grain buckets responsible for the remaining mozilla deficit.

For matching 512 KiB parents, measure exact KEPHIR stored bytes at
128/256/512 KiB grain using the qualified legacy inner backend. Also compute
a finer cheap fingerprint so ambiguous coarse buckets can be split without
globally enabling expensive probes.

Datasets:
- canonical Silesia files;
- deterministic Router Matrix v2 holdouts, scanned file-by-file.
"""
from pathlib import Path
import collections
import json
import shutil
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
sys.path.insert(0,str(ROOT/"research"/"packaging"))
import kephir_final as K
import router_matrix_v2 as RM

E=K.E
CH=512*1024

TARGETS={
    "l2:h7:z0:p1:s0",
    "l2:h5:z2:p1:s6",
    "l2:h5:z1:p3:s2",
}


def fine_bucket(parent):
    r2=E.residual_entropy(parent,2,step=64)
    r4=E.residual_entropy(parent,4,step=64)
    q=max(1,len(parent)//4)
    hs=[
        E.sample_entropy(parent[i:i+q],step=64)
        for i in range(0,len(parent),q)
    ]
    spread=(max(hs)-min(hs)) if hs else 0.0

    sample=parent[::64]
    unique=len(set(sample))
    transitions=0
    if len(sample)>1:
        transitions=sum(
            1 for a,b in zip(sample,sample[1:]) if a!=b
        )/(len(sample)-1)

    return (
        f"r2{min(31,int(r2*4))}:"
        f"r4{min(31,int(r4*4))}:"
        f"sp{min(15,int(spread*8))}:"
        f"u{min(15,unique//16)}:"
        f"tr{min(15,int(transitions*16))}"
    )


def exact_sizes(parent,tmp,tag):
    candidates=[]
    if len(parent)>128*1024:
        candidates.append(128*1024)
    if len(parent)>256*1024:
        candidates.append(256*1024)
    candidates.append(len(parent))

    out={}
    for g in sorted(set(candidates)):
        out[g]=E.measure_grain_exact(
            parent,g,tmp,0,f"{tag}_g{g}"
        )
    return out


def iter_files(root):
    if root.is_file():
        yield root
    else:
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                yield p


def audit_file(path,label,tmp,rows):
    raw=path.read_bytes()
    for pidx,start in enumerate(range(0,len(raw),CH)):
        parent=raw[start:start+CH]
        if len(parent)<256*1024:
            continue
        coarse=E.grain_feature_bucket(parent)
        if coarse not in TARGETS:
            continue

        sizes=exact_sizes(parent,tmp,f"{label}_{pidx}")
        best=min(sizes,key=lambda g:(sizes[g],g))
        baseline=E.choose_grain(parent)
        trusted,_,has_prior=K.trusted_grain(
            parent,K.merge_models(K.load_factory(True),{})
        )

        row={
            "dataset":label,
            "path":str(path),
            "parent_index":pidx,
            "raw_size":len(parent),
            "coarse":coarse,
            "fine":fine_bucket(parent),
            "baseline_grain":baseline,
            "trusted_grain":trusted,
            "has_trusted_prior":has_prior,
            "sizes":{str(k):v for k,v in sizes.items()},
            "best_grain":best,
            "best_bytes":sizes[best],
            "baseline_penalty":sizes[baseline]-sizes[best],
            "trusted_penalty":sizes[trusted]-sizes[best],
        }
        rows.append(row)

        print(
            "EXP104_PARENT",
            json.dumps(row,sort_keys=True),
            flush=True
        )


def main():
    corpus=ROOT/"corpora"/"silesia"
    if not corpus.exists():
        raise SystemExit("missing canonical Silesia")

    work=ROOT/"exp104_grain_oracle"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    tmp=work/"tmp"
    tmp.mkdir()

    rows=[]

    for p in sorted(corpus.iterdir()):
        if p.is_file():
            audit_file(p,"silesia/"+p.name,tmp,rows)

    matrix_root=work/"matrix"
    datasets=RM.materialize_matrix(
        matrix_root,
        corpus
    )
    # Silesia is already audited above. Scan non-Silesia matrix workloads.
    for name,root in datasets.items():
        if name=="silesia":
            continue
        root=Path(root)
        for p in iter_files(root):
            rel=p.relative_to(root)
            audit_file(
                p,
                f"matrix/{name}/{rel.as_posix()}",
                tmp,
                rows
            )

    by_coarse={}
    by_fine={}
    for row in rows:
        c=row["coarse"]
        f=c+"|"+row["fine"]
        for table,key in ((by_coarse,c),(by_fine,f)):
            a=table.setdefault(key,{
                "occurrences":0,
                "best_grains":collections.Counter(),
                "baseline_penalty":0,
                "trusted_penalty":0,
                "datasets":[],
            })
            a["occurrences"]+=1
            a["best_grains"][str(row["best_grain"])]+=1
            a["baseline_penalty"]+=row["baseline_penalty"]
            a["trusted_penalty"]+=row["trusted_penalty"]
            a["datasets"].append(row["dataset"])

    for table in (by_coarse,by_fine):
        for a in table.values():
            a["best_grains"]=dict(a["best_grains"])

    result={
        "experiment":"EXP-104",
        "targets":sorted(TARGETS),
        "rows":rows,
        "by_coarse":by_coarse,
        "by_fine":by_fine,
    }
    Path("exp104_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP104_OCCURRENCES",len(rows),flush=True)
    for key,a in sorted(by_coarse.items()):
        print(
            "EXP104_COARSE",key,
            json.dumps(a,sort_keys=True),
            flush=True
        )
    for key,a in sorted(by_fine.items()):
        if a["trusted_penalty"]>0:
            print(
                "EXP104_FINE",key,
                json.dumps(a,sort_keys=True),
                flush=True
            )
    print("EXP104_AUDIT_COMPLETE",flush=True)


if __name__=="__main__":
    main()
