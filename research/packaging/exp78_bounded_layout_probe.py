#!/usr/bin/env python3
"""
EXP-78 — Bounded Representative Layout Probe

KEPHIR 2 Global Router research.

Single conceptual change from EXP-77:
replace the metadata-only SMART/FLAT rule with a bounded representative
compression probe.

The probe never scales linearly with the full archive:
- stage 1: up to 2 MiB of representative content
- stage 2: up to 12 MiB when the archive is larger/uncertain

The full SMART and FLAT encodes are still executed by EXP-77 afterwards only
to measure the oracle and selection regret. They are evaluation work, not part
of the proposed production routing path.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K

OUT=ROOT/"exp78_layout_probe"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()

STAGE1_BUDGET=2*1024*1024
STAGE2_BUDGET=12*1024*1024
STAGE1_CONFIDENCE=0.05
MIN_FILE_SAMPLE=4096
STRATA=4

FLAT_MAGIC_BYTES=5  # four-byte magic + version byte


def files(root):
    return K.collect_directory(root)


def logical_bytes(root):
    return sum(p.stat().st_size for p in files(root))


def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()


def tracked_snapshot():
    dst=OUT/"repo_input"
    dst.mkdir()
    raw=subprocess.check_output(["git","ls-files","-z"])
    for item in raw.split(b"\0"):
        if not item:
            continue
        p=Path(item.decode("utf-8"))
        q=dst/p
        q.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():
            q.write_bytes(os.readlink(p).encode("utf-8"))
        else:
            shutil.copyfile(p,q)
    return dst


def read_window(path,offset,length):
    with path.open("rb") as f:
        f.seek(offset)
        return f.read(length)


def stratified_sample(path,budget):
    size=path.stat().st_size
    if size<=budget:
        return path.read_bytes()
    if budget<=0:
        return b""

    parts=min(STRATA,max(1,budget//MIN_FILE_SAMPLE))
    part=max(1,budget//parts)
    maxoff=max(0,size-part)
    offsets=[]
    if parts==1:
        offsets=[maxoff//2]
    else:
        for i in range(parts):
            offsets.append((maxoff*i)//(parts-1))

    out=bytearray()
    seen=set()
    for off in offsets:
        if off in seen:
            continue
        seen.add(off)
        need=min(part,budget-len(out))
        if need<=0:
            break
        out.extend(read_window(path,off,need))
    return bytes(out[:budget])


def choose_file_budgets(fs,total_budget):
    sizes=[p.stat().st_size for p in fs]
    total=sum(sizes)
    if total<=total_budget:
        return sizes

    n=max(1,len(fs))
    base=max(MIN_FILE_SAMPLE,total_budget//n)
    budgets=[min(sz,base) for sz in sizes]
    used=sum(budgets)

    # Spend remaining budget proportionally on files that still have unseen data.
    remain=max(0,total_budget-used)
    while remain>0:
        eligible=[i for i,sz in enumerate(sizes) if budgets[i]<sz]
        if not eligible:
            break
        share=max(1,remain//len(eligible))
        progressed=0
        for i in eligible:
            add=min(share,sizes[i]-budgets[i],remain)
            if add<=0:
                continue
            budgets[i]+=add
            remain-=add
            progressed+=add
            if remain<=0:
                break
        if progressed==0:
            break

    # For extremely high file counts MIN_FILE_SAMPLE can exceed the budget.
    # Trim deterministically from the end until the global cap is respected.
    over=sum(budgets)-total_budget
    if over>0:
        for i in range(len(budgets)-1,-1,-1):
            reducible=max(0,budgets[i]-min(sizes[i],1))
            cut=min(reducible,over)
            budgets[i]-=cut
            over-=cut
            if over<=0:
                break
    return budgets


def make_probe_tree(root,label,budget):
    dst=OUT/f"{label}_probe_{budget}"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    fs=files(root)
    budgets=choose_file_budgets(fs,budget)
    sampled=0
    for p,b in zip(fs,budgets):
        rel=p.relative_to(root)
        q=dst/rel
        q.parent.mkdir(parents=True,exist_ok=True)
        data=stratified_sample(p,b)
        q.write_bytes(data)
        sampled+=len(data)
    return dst,sampled


def varint_len(v):
    n=1
    while v>=128:
        v >>= 7
        n += 1
    return n


def build_flat_manifest(records):
    out=bytearray()
    K.put_varint(out,len(records))
    prev=b""
    for rel,size in records:
        p=rel.encode("utf-8")
        cp=K.common_prefix(prev,p)
        suffix=p[cp:]
        K.put_varint(out,cp)
        K.put_varint(out,len(suffix))
        out.extend(suffix)
        K.put_varint(out,size)
        prev=p
    return bytes(out)


def fresh_factory_model():
    return K.merge_models(K.load_factory(True),{})


def probe_flat(root,label):
    fs=files(root)
    records=[]
    payload=bytearray()
    for p in fs:
        b=p.read_bytes()
        records.append((p.relative_to(root).as_posix(),len(b)))
        payload.extend(b)
    manifest=build_flat_manifest(records)

    with tempfile.TemporaryDirectory(prefix="exp78_flat_") as td:
        td=Path(td)
        raw=td/"probe.raw"
        inner=td/"probe.k75"
        raw.write_bytes(payload)
        stats=K.final_encode(raw,inner,td/"engine",fresh_factory_model())
        blob_bytes=inner.stat().st_size

    archive_bytes=(
        FLAT_MAGIC_BYTES
        + varint_len(len(manifest)) + len(manifest)
        + varint_len(len(payload))
        + varint_len(blob_bytes) + blob_bytes
    )
    return {
        "layout":"flat",
        "archive_bytes":archive_bytes,
        "sample_payload_bytes":len(payload),
        "manifest_bytes":len(manifest),
        "engine":stats,
    }


def probe_smart(root,label):
    with tempfile.TemporaryDirectory(prefix="exp78_smart_") as td:
        td=Path(td)
        arc=td/"probe.kpf"
        engine_tmp=td/"engine"
        engine_tmp.mkdir(parents=True,exist_ok=True)
        stats=K.compress_directory(root,arc,fresh_factory_model(),engine_tmp)
        size=arc.stat().st_size
    return {
        "layout":"smart",
        "archive_bytes":size,
        "sample_payload_bytes":logical_bytes(root),
        "manifest_bytes":stats["manifest_bytes"],
        "engine":stats["engine"],
        "groups":stats["groups"],
    }


def run_probe(root,label,budget):
    sample_root,sampled=make_probe_tree(root,label,budget)
    t0=time.perf_counter()
    smart=probe_smart(sample_root,label)
    flat=probe_flat(sample_root,label)
    elapsed=time.perf_counter()-t0

    selected="smart" if smart["archive_bytes"]<flat["archive_bytes"] else "flat"
    best=min(smart["archive_bytes"],flat["archive_bytes"])
    worst=max(smart["archive_bytes"],flat["archive_bytes"])
    margin=(worst-best)/best if best else 0.0
    return {
        "budget_bytes":budget,
        "sampled_bytes":sampled,
        "probe_time_s":elapsed,
        "selected_layout":selected,
        "relative_margin":margin,
        "smart":smart,
        "flat":flat,
    }


def route_with_probe(root,label):
    total=logical_bytes(root)
    stage1=run_probe(root,label+"_s1",min(STAGE1_BUDGET,total))

    # Full sample means the probe is already exact for this input.
    if stage1["sampled_bytes"]>=total:
        return {
            "selected_layout":stage1["selected_layout"],
            "reason":"stage1-full-input",
            "total_probe_time_s":stage1["probe_time_s"],
            "stages":[stage1],
        }

    # Only accept a very strong small-sample signal. Otherwise spend the bounded
    # stage-2 budget. Large archives therefore receive a more representative
    # probe while the cost remains independent of archive size.
    if total<=STAGE2_BUDGET and stage1["relative_margin"]>=STAGE1_CONFIDENCE:
        return {
            "selected_layout":stage1["selected_layout"],
            "reason":"stage1-high-confidence",
            "total_probe_time_s":stage1["probe_time_s"],
            "stages":[stage1],
        }

    stage2=run_probe(root,label+"_s2",min(STAGE2_BUDGET,total))
    return {
        "selected_layout":stage2["selected_layout"],
        "reason":"stage2-representative-probe",
        "total_probe_time_s":stage1["probe_time_s"]+stage2["probe_time_s"],
        "stages":[stage1,stage2],
    }


os.environ["KEPHIR_WORKERS"]="16"

repo=tracked_snapshot()
silesia=ROOT/"corpora"/"silesia"
if not silesia.exists():
    raise SystemExit("Silesia missing")

routes={
    "repository":route_with_probe(repo,"repository"),
    "silesia":route_with_probe(silesia,"silesia"),
}

# Run EXP-77 as the full-layout oracle/evaluation harness. This is deliberately
# separate from the bounded proposed routing path above.
subprocess.run(
    [sys.executable,"research/packaging/exp77_adaptive_layout.py"],
    check=True,
)
exp77=json.loads(Path("exp77_results.json").read_text())

result={
    "experiment":"EXP-78",
    "change":"bounded-representative-layout-probe",
    "stage1_budget_bytes":STAGE1_BUDGET,
    "stage2_budget_bytes":STAGE2_BUDGET,
    "datasets":{},
}

old_total=0
new_total=0
for label,route in routes.items():
    full=exp77["datasets"][label]
    selected=route["selected_layout"]
    oracle=full["oracle_layout"]
    oracle_bytes=full[oracle]["archive_bytes"]
    selected_bytes=full[selected]["archive_bytes"]
    new_regret=selected_bytes-oracle_bytes
    old_regret=full["selection_regret_bytes"]
    old_total+=old_regret
    new_total+=new_regret

    result["datasets"][label]={
        "logical_bytes":full["meta"]["logical_bytes"],
        "probe":route,
        "exp77_selected_layout":full["selected_layout"],
        "probe_selected_layout":selected,
        "oracle_layout":oracle,
        "exp77_regret_bytes":old_regret,
        "probe_regret_bytes":new_regret,
        "regret_improvement_bytes":old_regret-new_regret,
        "full_smart":{
            "archive_bytes":full["smart"]["archive_bytes"],
            "ratio":full["smart"]["ratio"],
            "comp_time_s":full["smart"]["comp_time_s"],
            "dec_time_s":full["smart"]["dec_time_s"],
            "sha_ok":full["smart"]["sha_ok"],
        },
        "full_flat":{
            "archive_bytes":full["flat"]["archive_bytes"],
            "ratio":full["flat"]["ratio"],
            "comp_time_s":full["flat"]["comp_time_s"],
            "dec_time_s":full["flat"]["dec_time_s"],
            "sha_ok":full["flat"]["sha_ok"],
        },
    }

result["aggregate"]={
    "exp77_regret_bytes":old_total,
    "probe_regret_bytes":new_total,
    "regret_improvement_bytes":old_total-new_total,
}

Path("exp78_results.json").write_text(json.dumps(result,indent=2,sort_keys=True))
print("EXP78_RESULTS",json.dumps(result,sort_keys=True),flush=True)
