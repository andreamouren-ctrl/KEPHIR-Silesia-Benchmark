#!/usr/bin/env python3
"""
EXP-86 — Cheap Cross-File Groupability Estimator

Purpose:
replace compression-based SMART/FLAT probing with a cheap structural estimator.

The estimator measures whether content grouping has a real cross-file reuse
opportunity:
- number of content families;
- bytes belonging to families represented by at least two files;
- dominant-family byte fraction;
- average file size.

No SMART/FLAT micro-compression is performed for the routing decision.

For every dataset:
- run bounded EXP-79 routing;
- encode full SMART and FLAT layouts;
- verify exact roundtrip for both layouts;
- compare selected layout with the full oracle;
- record regret and routing overhead.
"""
from pathlib import Path
import hashlib
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
sys.path.insert(0,str(ROOT/"research"/"packaging"))
import kephir_final as K
import router_matrix_v1 as RM

OUT=ROOT/"exp86_groupability_estimator"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
INPUTS=OUT/"inputs"
INPUTS.mkdir()

FLAT_MAGIC=b"K86F"
FLAT_VERSION=1

STAGE1_BUDGET=512*1024
STAGE2_BUDGET=2*1024*1024
STAGE1_CONFIDENCE=0.02
STAGE2_CONFIDENCE=0.002
DIVERSITY_MIN_GROUPS=3
DIVERSITY_MAX_DOMINANT_FILE_FRACTION=0.75
DIVERSITY_MAX_DOMINANT_BYTE_FRACTION=0.80
DIVERSITY_MIN_LOGICAL_BYTES=8*1024*1024
MIN_FILE_SAMPLE=4096
STRATA=4
SMALL_FULL_PROBE_LIMIT=1024*1024

GROUPABILITY_MIN_AVG_FILE_BYTES=512*1024
GROUPABILITY_MIN_REPEATABLE_BYTE_FRACTION=0.60
GROUPABILITY_MAX_DOMINANT_BYTE_FRACTION=0.75


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


def verify_tree(src,dst):
    a=files(src)
    b=files(dst)
    ar=[p.relative_to(src).as_posix() for p in a]
    br=[p.relative_to(dst).as_posix() for p in b]
    if ar!=br:
        return False
    return all(sha256_file(p)==sha256_file(dst/p.relative_to(src)) for p in a)


def fresh_factory_model():
    return K.merge_models(K.load_factory(True),{})


def tracked_snapshot():
    dst=INPUTS/"repository"
    dst.mkdir()
    raw=subprocess.check_output(["git","ls-files","-z"])
    for item in raw.split(b"\0"):
        if not item:
            continue
        p=Path(item.decode())
        q=dst/p
        q.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():
            q.write_bytes(os.readlink(p).encode())
        else:
            shutil.copyfile(p,q)
    return dst


def put_flat_manifest(records):
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


def parse_flat_manifest(buf):
    pos=0
    count,pos=K.get_varint(buf,pos)
    prev=b""
    records=[]
    for _ in range(count):
        cp,pos=K.get_varint(buf,pos)
        sl,pos=K.get_varint(buf,pos)
        suffix=buf[pos:pos+sl]
        pos+=sl
        size,pos=K.get_varint(buf,pos)
        p=prev[:cp]+suffix
        prev=p
        records.append((p.decode("utf-8"),size))
    if pos!=len(buf):
        raise ValueError("flat manifest trailing bytes")
    return records


def compress_flat(root,out):
    records=[]
    payload=bytearray()
    for p in files(root):
        data=p.read_bytes()
        records.append((p.relative_to(root).as_posix(),len(data)))
        payload.extend(data)
    manifest=put_flat_manifest(records)

    with tempfile.TemporaryDirectory(prefix="exp86_flat_") as td:
        td=Path(td)
        raw=td/"flat.raw"
        inner=td/"flat.k75"
        raw.write_bytes(payload)
        stats=K.final_encode(raw,inner,td/"engine",fresh_factory_model())
        blob=inner.read_bytes()

    packed=bytearray(FLAT_MAGIC)
    packed.append(FLAT_VERSION)
    K.put_varint(packed,len(manifest))
    packed.extend(manifest)
    K.put_varint(packed,len(payload))
    K.put_varint(packed,len(blob))
    packed.extend(blob)
    out.write_bytes(packed)
    return {"manifest_bytes":len(manifest),"engine":stats}


def extract_flat(arc,out):
    b=arc.read_bytes()
    if b[:4]!=FLAT_MAGIC:
        raise ValueError("not EXP86 flat")
    pos=4
    version=b[pos]
    pos+=1
    if version!=FLAT_VERSION:
        raise ValueError("unsupported EXP86 flat version")
    ml,pos=K.get_varint(b,pos)
    manifest=b[pos:pos+ml]
    pos+=ml
    rawlen,pos=K.get_varint(b,pos)
    cl,pos=K.get_varint(b,pos)
    blob=b[pos:pos+cl]
    pos+=cl
    if pos!=len(b):
        raise ValueError("flat trailing bytes")
    records=parse_flat_manifest(manifest)

    with tempfile.TemporaryDirectory(prefix="exp86_flat_dec_") as td:
        td=Path(td)
        inner=td/"flat.k75"
        raw=td/"flat.raw"
        inner.write_bytes(blob)
        K.final_decode(inner,raw,td/"engine")
        payload=raw.read_bytes()

    if len(payload)!=rawlen:
        raise ValueError("flat raw length mismatch")

    out.mkdir(parents=True,exist_ok=True)
    cursor=0
    for rel,size in records:
        target=K.safe_target(out,rel)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(payload[cursor:cursor+size])
        cursor+=size
    if cursor!=len(payload):
        raise ValueError("flat reconstruction length mismatch")


def run_smart(root,label):
    arc=OUT/f"{label}.smart.kpf"
    dest=OUT/f"{label}.smart.out"
    t0=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="exp86_smart_") as td:
        stats=K.compress_directory(root,arc,fresh_factory_model(),Path(td))
    comp=time.perf_counter()-t0
    t0=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="exp86_smart_dec_") as td:
        K.extract_archive(arc,dest,Path(td))
    dec=time.perf_counter()-t0
    ok=verify_tree(root,dest)
    if not ok:
        raise RuntimeError(label+" SMART roundtrip mismatch")
    raw=logical_bytes(root)
    return {
        "layout":"smart",
        "archive_bytes":arc.stat().st_size,
        "ratio":arc.stat().st_size/raw if raw else 0.0,
        "comp_time_s":comp,
        "dec_time_s":dec,
        "sha_ok":ok,
        "stats":stats,
    }


def run_flat(root,label):
    arc=OUT/f"{label}.flat.k80f"
    dest=OUT/f"{label}.flat.out"
    t0=time.perf_counter()
    stats=compress_flat(root,arc)
    comp=time.perf_counter()-t0
    t0=time.perf_counter()
    extract_flat(arc,dest)
    dec=time.perf_counter()-t0
    ok=verify_tree(root,dest)
    if not ok:
        raise RuntimeError(label+" FLAT roundtrip mismatch")
    raw=logical_bytes(root)
    return {
        "layout":"flat",
        "archive_bytes":arc.stat().st_size,
        "ratio":arc.stat().st_size/raw if raw else 0.0,
        "comp_time_s":comp,
        "dec_time_s":dec,
        "sha_ok":ok,
        "stats":stats,
    }


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
    offsets=[maxoff//2] if parts==1 else [(maxoff*i)//(parts-1) for i in range(parts)]
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
    dst=OUT/f"{label}.probe.{budget}"
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


def diversity_prefers_smart(diversity,total):
    return (
        total>=DIVERSITY_MIN_LOGICAL_BYTES
        and diversity["group_count"]>=DIVERSITY_MIN_GROUPS
        and diversity["dominant_file_fraction"]<=DIVERSITY_MAX_DOMINANT_FILE_FRACTION
        and diversity["dominant_byte_fraction"]<=DIVERSITY_MAX_DOMINANT_BYTE_FRACTION
    )


def probe_layout(root,label,budget):
    sample_root,sampled=make_probe_tree(root,label,budget)
    diversity=content_diversity(sample_root)
    t0=time.perf_counter()
    smart=run_smart(sample_root,label+".probe.smart")
    flat=run_flat(sample_root,label+".probe.flat")
    elapsed=time.perf_counter()-t0
    selected="smart" if smart["archive_bytes"]<flat["archive_bytes"] else "flat"
    best=min(smart["archive_bytes"],flat["archive_bytes"])
    worst=max(smart["archive_bytes"],flat["archive_bytes"])
    return {
        "budget_bytes":budget,
        "sampled_bytes":sampled,
        "probe_time_s":elapsed,
        "selected_layout":selected,
        "relative_margin":((worst-best)/best if best else 0.0),
        "diversity":diversity,
        "smart_bytes":smart["archive_bytes"],
        "flat_bytes":flat["archive_bytes"],
    }


def groupability_features(root):
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

    repeated_bytes=sum(
        by_bytes[g] for g,count in by_files.items() if count>=2
    )
    dominant_bytes=max(by_bytes.values(),default=0)
    multi_file_groups=sum(1 for count in by_files.values() if count>=2)

    return {
        "group_count":len(by_files),
        "multi_file_groups":multi_file_groups,
        "files_by_group":dict(sorted(by_files.items())),
        "bytes_by_group":dict(sorted(by_bytes.items())),
        "repeatable_byte_fraction":(
            repeated_bytes/total_bytes if total_bytes else 0.0
        ),
        "dominant_byte_fraction":(
            dominant_bytes/total_bytes if total_bytes else 0.0
        ),
        "average_file_bytes":(
            total_bytes/total_files if total_files else 0.0
        ),
    }


def route_exp86(root,label):
    features=groupability_features(root)

    if features["group_count"]<=1:
        return "flat","single-content-class-dominance",[],features

    smart_candidate=(
        features["average_file_bytes"]>=GROUPABILITY_MIN_AVG_FILE_BYTES
        and features["repeatable_byte_fraction"]>=GROUPABILITY_MIN_REPEATABLE_BYTE_FRACTION
        and features["dominant_byte_fraction"]<=GROUPABILITY_MAX_DOMINANT_BYTE_FRACTION
    )

    if smart_candidate:
        return "smart","cross-file-groupability-smart",[],features

    return "flat","cross-file-groupability-flat",[],features


def write_repeat(path,pattern,size):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not pattern:
        pattern=b"\x00"
    q,r=divmod(size,len(pattern))
    path.write_bytes(pattern*q+pattern[:r])


def make_many_tiny_source():
    root=INPUTS/"many_tiny_source"
    root.mkdir()
    base=(
        b"int compute(int x){ return (x*17)+3; }\n"
        b"struct Item { int a; int b; int c; };\n"
        b"if(value<limit){value+=step;}else{value-=step;}\n"
    )
    for i in range(1024):
        payload=(base+f"// unit {i:04d}\n".encode())*32
        (root/f"f{i:04d}.dat").write_bytes(payload)
    return root


def make_homogeneous_large():
    root=INPUTS/"homogeneous_large"
    root.mkdir()
    pattern=(
        b"The same project record is repeated across several large files. "
        b"Cross-file redundancy should remain highly visible to a solid stream.\n"
    )
    for i in range(4):
        write_repeat(root/f"f{i}.dat",pattern,3*1024*1024)
    return root


def make_mixed_content():
    root=INPUTS/"mixed_content"
    root.mkdir()
    one=1024*1024
    write_repeat(root/"a.dat",b"int f(int x){return x*x+17;}\n",one)
    write_repeat(root/"b.dat",b"ordinary prose words and spaces form a natural language paragraph.\n",one)
    write_repeat(root/"c.dat",b"name: value\npath: /var/data\nmode: fast\n",one)
    write_repeat(root/"d.dat",(b"\x00"*16+b"\xff"*112),one)
    write_repeat(root/"e.dat",bytes(range(16)),one)
    write_repeat(root/"f.dat",bytes(range(64)),one)
    rng=random.Random(8001)
    (root/"g.dat").write_bytes(rng.randbytes(one))
    write_repeat(root/"h.dat",b"0123456789!?.,|~ABCxyz",one)
    return root


def make_incompressible():
    root=INPUTS/"incompressible"
    root.mkdir()
    rng=random.Random(8002)
    for i in range(4):
        (root/f"f{i}.dat").write_bytes(rng.randbytes(2*1024*1024))
    return root


def make_zero_rich():
    root=INPUTS/"zero_rich"
    root.mkdir()
    pattern=(
        b"\x00\x00\x00\x00"
        b"\x01\x00\x00\x00"
        b"\x02\x00\x00\x00"
        b"\x03\x00\x00\x00"
    )
    for i in range(8):
        write_repeat(root/f"f{i}.dat",pattern,1024*1024)
    return root


def make_redundant_backup():
    root=INPUTS/"redundant_backup"
    root.mkdir()
    block=(
        b"backup-record|customer=000001|state=active|timestamp=2026-09-26\n"
        b"backup-record|customer=000002|state=active|timestamp=2026-09-26\n"
    )
    common=(block*((512*1024)//len(block)+1))[:512*1024]
    for i in range(16):
        tail=(f"snapshot={i:02d}\n".encode()*1024)
        data=bytearray(common)
        data[-len(tail):]=tail
        (root/f"f{i}.dat").write_bytes(data)
    return root


os.environ["KEPHIR_WORKERS"]="16"

datasets=RM.materialize_matrix(INPUTS,ROOT/"corpora"/"silesia")

if not datasets["silesia"].exists():
    raise SystemExit("Silesia missing")

result={
    "experiment":"EXP-86",
    "change":"cheap-cross-file-groupability-estimator",
    "thresholds":{
        "min_avg_file_bytes":GROUPABILITY_MIN_AVG_FILE_BYTES,
        "min_repeatable_byte_fraction":GROUPABILITY_MIN_REPEATABLE_BYTE_FRACTION,
        "max_dominant_byte_fraction":GROUPABILITY_MAX_DOMINANT_BYTE_FRACTION,
    },
    "datasets":{},
}

total_regret=0
correct=0
total_probe_s=0.0

for label,root in datasets.items():
    print("EXP86_BEGIN",label,flush=True)
    total=logical_bytes(root)
    fs=files(root)
    sizes=[p.stat().st_size for p in fs]

    t0=time.perf_counter()
    selected,reason,stages,groupability=route_exp86(root,label)
    routing_s=time.perf_counter()-t0

    smart=run_smart(root,label)
    flat=run_flat(root,label)
    options={"smart":smart,"flat":flat}
    oracle=min(options,key=lambda k:options[k]["archive_bytes"])
    regret=options[selected]["archive_bytes"]-options[oracle]["archive_bytes"]
    total_regret+=regret
    correct+=int(selected==oracle)
    total_probe_s+=routing_s

    result["datasets"][label]={
        "meta":{
            "files":len(fs),
            "logical_bytes":total,
            "avg_file_bytes":(total/len(fs) if fs else 0.0),
            "median_file_bytes":statistics.median(sizes) if sizes else 0.0,
            "small_file_fraction":(sum(x<64*1024 for x in sizes)/len(sizes) if sizes else 0.0),
        },
        "selected_layout":selected,
        "selection_reason":reason,
        "oracle_layout":oracle,
        "selection_regret_bytes":regret,
        "routing_time_s":routing_s,
        "probe_stages":stages,
        "groupability":groupability,
        "smart":smart,
        "flat":flat,
        "flat_minus_smart_bytes":flat["archive_bytes"]-smart["archive_bytes"],
    }
    print(
        "EXP86_DATASET",label,
        "SELECTED",selected,
        "ORACLE",oracle,
        "REGRET",regret,
        "REASON",reason,
        "ROUTING_S",routing_s,
        "SMART",smart["archive_bytes"],
        "FLAT",flat["archive_bytes"],
        flush=True,
    )

result["aggregate"]={
    "datasets":len(datasets),
    "correct_selections":correct,
    "selection_accuracy":correct/len(datasets),
    "total_regret_bytes":total_regret,
    "total_routing_time_s":total_probe_s,
}

Path("exp86_results.json").write_text(json.dumps(result,indent=2,sort_keys=True))
print("EXP86_AGGREGATE",json.dumps(result["aggregate"],sort_keys=True),flush=True)
print("EXP86_SHA_ALL_PASS",flush=True)
