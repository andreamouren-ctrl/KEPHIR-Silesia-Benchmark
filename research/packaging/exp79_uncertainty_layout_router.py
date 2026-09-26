#!/usr/bin/env python3
"""
EXP-79 — Uncertainty-Aware Layout Router

KEPHIR 2 Global Router research: confidence-aware routing.

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

OUT=ROOT/"exp79_uncertainty_router"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()

STAGE1_BUDGET=2*1024*1024
STAGE2_BUDGET=12*1024*1024
STAGE1_CONFIDENCE=0.02\nSTAGE2_CONFIDENCE=0.002\nDIVERSITY_MIN_GROUPS=3\nDIVERSITY_MAX_DOMINANT_FILE_FRACTION=0.75\nDIVERSITY_MAX_DOMINANT_BYTE_FRACTION=0.80\nDIVERSITY_MIN_LOGICAL_BYTES=8*1024*1024
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


def content_diversity(root):
    by_files={}
    by_bytes={}
    total_files=0
    total_bytes=0
    for p in files(root):
        data=p.read_bytes()
        group=K.classify(data)
        by_files[group]=by_files.get(group,0)+1
        by_bytes[group]=by_bytes.get(group,0)+len(data)
        total_files+=1
        total_bytes+=len(data)

    dominant_files=max(by_files.values(),default=0)
    dominant_bytes=max(by_bytes.values(),default=0)
    return {
        "group_count":len(by_files),
        "files_by_group":dict(sorted(by_files.items())),
        "bytes_by_group":dict(sorted(by_bytes.items())),
        "dominant_file_fraction":dominant_files/total_files if total_files else 0.0,
        "dominant_byte_fraction":dominant_bytes/total_bytes if total_bytes else 0.0,
    }


def diversity_prefers_smart(diversity,total_logical):
    return (
        total_logical>=DIVERSITY_MIN_LOGICAL_BYTES
        and diversity["group_count"]>=DIVERSITY_MIN_GROUPS
        and diversity["dominant_file_fraction"]<=DIVERSITY_MAX_DOMINANT_FILE_FRACTION
        and diversity["dominant_byte_fraction"]<=DIVERSITY_MAX_DOMINANT_BYTE_FRACTION
    )


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

    with tempfile.TemporaryDirectory(prefix="exp79_flat_") as td:
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
    with tempfile.TemporaryDirectory(prefix="exp79_smart_") as td:
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
    diversity=content_diversity(sample_root)
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
        "diversity":diversity,
        "smart":smart,
        "flat":flat,
    }


def route_with_probe(root,label):
    total=logical_bytes(root)
    stage1=run_probe(root,label+"_s1",min(STAGE1_BUDGET,total))

    # A full-input probe is exact for the current directory.
    if stage1["sampled_bytes"]>=total:
        return {
            "selected_layout":stage1["selected_layout"],
            "reason":"stage1-full-input",
            "total_probe_time_s":stage1["probe_time_s"],
            "stages":[stage1],
        }

    # Trust only a material difference. Tiny sampled deltas are not predictive
    # enough for a full archive and were the failure mode observed in EXP-78.
    if stage1["relative_margin"]>=STAGE1_CONFIDENCE:
        return {
            "selected_layout":stage1["selected_layout"],
            "reason":"stage1-strong-margin",
            "total_probe_time_s":stage1["probe_time_s"],
            "stages":[stage1],
        }

    # If the sample is ambiguous but clearly contains several substantial
    # content families, prefer SMART grouping. This is not extension-based:
    # classes come from KEPHIR's content-first byte classifier.
    if diversity_prefers_smart(stage1["diversity"],total):
        return {
            "selected_layout":"smart",
            "reason":"stage1-ambiguous-content-diversity",
            "total_probe_time_s":stage1["probe_time_s"],
            "stages":[stage1],
        }

    # Otherwise spend the larger bounded budget.
    stage2=run_probe(root,label+"_s2",min(STAGE2_BUDGET,total))
    if stage2["relative_margin"]>=STAGE2_CONFIDENCE:
        selected=stage2["selected_layout"]
        reason="stage2-material-margin"
    elif diversity_prefers_smart(stage2["diversity"],total):
        selected="smart"
        reason="stage2-ambiguous-content-diversity"
    else:
        selected=stage2["selected_layout"]
        reason="stage2-ambiguous-probe"

    return {
        "selected_layout":selected,
        "reason":reason,
        "total_probe_time_s":stage1["probe_time_s"]+stage2["probe_time_s"],
        "stages":[stage1,stage2],
    }

