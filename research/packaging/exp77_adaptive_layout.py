#!/usr/bin/env python3
"""
EXP-77 — Adaptive Directory Layout Router

One conceptual change only:
choose the directory packing layout before compression.

Layouts:
- smart: KEPHIR 1.0 RC content-first grouping (EXP-76)
- flat: one reversible solid stream + compact path/size manifest

The router itself uses only cheap file metadata.  The experiment also encodes
both layouts so we can measure oracle regret without changing the inner EXP-75
compression engine or Factory Knowledge.
"""
from pathlib import Path
import hashlib, json, os, shutil, statistics, subprocess, sys, tempfile, time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K

OUT=ROOT/"exp77_adaptive_layout"
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()

FLAT_MAGIC=b"K77F"
FLAT_VERSION=1

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def files(root):
    return K.collect_directory(root)

def logical_bytes(root):
    return sum(p.stat().st_size for p in files(root))

def tracked_snapshot():
    dst=OUT/"repo_input"; dst.mkdir()
    raw=subprocess.check_output(["git","ls-files","-z"])
    for item in raw.split(b"\0"):
        if not item: continue
        p=Path(item.decode())
        q=dst/p
        q.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():
            q.write_bytes(os.readlink(p).encode())
        else:
            shutil.copyfile(p,q)
    return dst

def build_flat_manifest(records):
    out=bytearray(); K.put_varint(out,len(records)); prev=b""
    for rel,size in records:
        p=rel.encode("utf-8")
        cp=K.common_prefix(prev,p); suf=p[cp:]
        K.put_varint(out,cp); K.put_varint(out,len(suf)); out.extend(suf)
        K.put_varint(out,size)
        prev=p
    return bytes(out)

def parse_flat_manifest(buf):
    pos=0; count,pos=K.get_varint(buf,pos); prev=b""; records=[]
    for _ in range(count):
        cp,pos=K.get_varint(buf,pos)
        sl,pos=K.get_varint(buf,pos)
        suf=buf[pos:pos+sl]; pos+=sl
        size,pos=K.get_varint(buf,pos)
        p=prev[:cp]+suf; prev=p
        records.append((p.decode("utf-8"),size))
    if pos!=len(buf):
        raise ValueError("flat manifest trailing bytes")
    return records

def fresh_factory_model():
    return K.merge_models(K.load_factory(True),{})

def compress_flat(root,out):
    fs=files(root)
    records=[]
    payload=bytearray()
    for p in fs:
        b=p.read_bytes()
        records.append((p.relative_to(root).as_posix(),len(b)))
        payload.extend(b)
    manifest=build_flat_manifest(records)

    with tempfile.TemporaryDirectory(prefix="exp77_flat_") as td:
        td=Path(td)
        raw=td/"flat.raw"; inner=td/"flat.k75"
        raw.write_bytes(payload)
        stats=K.final_encode(raw,inner,td/"engine",fresh_factory_model())
        blob=inner.read_bytes()

    data=bytearray(FLAT_MAGIC)
    data.append(FLAT_VERSION)
    K.put_varint(data,len(manifest)); data.extend(manifest)
    K.put_varint(data,len(payload)); K.put_varint(data,len(blob)); data.extend(blob)
    out.write_bytes(data)
    return {"manifest_bytes":len(manifest),"engine":stats}

def extract_flat(arc,out):
    b=arc.read_bytes(); pos=0
    if b[:4]!=FLAT_MAGIC: raise ValueError("not EXP77 flat")
    pos=4
    version=b[pos]; pos+=1
    if version!=FLAT_VERSION: raise ValueError("unsupported EXP77 flat version")
    ml,pos=K.get_varint(b,pos)
    manifest=b[pos:pos+ml]; pos+=ml
    rawlen,pos=K.get_varint(b,pos)
    cl,pos=K.get_varint(b,pos)
    blob=b[pos:pos+cl]; pos+=cl
    if pos!=len(b): raise ValueError("flat archive trailing bytes")
    records=parse_flat_manifest(manifest)

    with tempfile.TemporaryDirectory(prefix="exp77_flat_dec_") as td:
        td=Path(td)
        inner=td/"flat.k75"; raw=td/"flat.raw"
        inner.write_bytes(blob)
        K.final_decode(inner,raw,td/"engine")
        payload=raw.read_bytes()
    if len(payload)!=rawlen: raise ValueError("flat payload length mismatch")

    out.mkdir(parents=True,exist_ok=True)
    cursor=0
    for rel,size in records:
        target=K.safe_target(out,rel)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(payload[cursor:cursor+size])
        cursor+=size
    if cursor!=len(payload): raise ValueError("flat reconstruction length mismatch")

def verify_tree(src,dst):
    a=files(src); b=files(dst)
    ar=[p.relative_to(src).as_posix() for p in a]
    br=[p.relative_to(dst).as_posix() for p in b]
    if ar!=br: return False
    return all(sha256_file(p)==sha256_file(dst/p.relative_to(src)) for p in a)

def route_layout(root):
    fs=files(root)
    sizes=[p.stat().st_size for p in fs]
    total=sum(sizes); n=len(sizes)
    avg=total/n if n else 0
    small=sum(s<64*1024 for s in sizes)/n if n else 0.0
    # Metadata-only zero-probe rule:
    # few, predominantly large files benefit from a single shared solid context;
    # many small files keep EXP-76 homogeneous grouping.
    layout="flat" if (n<=32 and avg>=1024*1024 and small<=0.25) else "smart"
    return layout,{
        "files":n,
        "logical_bytes":total,
        "avg_file_bytes":avg,
        "median_file_bytes":statistics.median(sizes) if sizes else 0,
        "small_file_fraction":small,
    }

def run_smart(root,label):
    arc=OUT/f"{label}.smart.kpf"
    dest=OUT/f"{label}.smart.out"
    t0=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="exp77_smart_") as td:
        stats=K.compress_directory(root,arc,fresh_factory_model(),Path(td))
    ct=time.perf_counter()-t0
    t0=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="exp77_smart_dec_") as td:
        K.extract_archive(arc,dest,Path(td))
    dt=time.perf_counter()-t0
    ok=verify_tree(root,dest)
    if not ok: raise RuntimeError(label+" smart roundtrip mismatch")
    return {"layout":"smart","archive_bytes":arc.stat().st_size,"ratio":arc.stat().st_size/logical_bytes(root),
            "comp_time_s":ct,"dec_time_s":dt,"sha_ok":ok,"stats":stats}

def run_flat(root,label):
    arc=OUT/f"{label}.flat.k77f"
    dest=OUT/f"{label}.flat.out"
    t0=time.perf_counter(); stats=compress_flat(root,arc); ct=time.perf_counter()-t0
    t0=time.perf_counter(); extract_flat(arc,dest); dt=time.perf_counter()-t0
    ok=verify_tree(root,dest)
    if not ok: raise RuntimeError(label+" flat roundtrip mismatch")
    return {"layout":"flat","archive_bytes":arc.stat().st_size,"ratio":arc.stat().st_size/logical_bytes(root),
            "comp_time_s":ct,"dec_time_s":dt,"sha_ok":ok,"stats":stats}

os.environ["KEPHIR_WORKERS"]="16"
repo=tracked_snapshot()
silesia=ROOT/"corpora"/"silesia"
if not silesia.exists(): raise SystemExit("Silesia missing")

result={"experiment":"EXP-77","change":"adaptive-directory-layout","datasets":{}}
for label,root in (("repository",repo),("silesia",silesia)):
    t0=time.perf_counter(); selected,meta=route_layout(root); routing=time.perf_counter()-t0
    smart=run_smart(root,label)
    flat=run_flat(root,label)
    options={"smart":smart,"flat":flat}
    oracle=min(options,key=lambda k:options[k]["archive_bytes"])
    chosen=options[selected]
    result["datasets"][label]={
        "meta":meta,
        "routing_time_s":routing,
        "selected_layout":selected,
        "oracle_layout":oracle,
        "selection_regret_bytes":chosen["archive_bytes"]-options[oracle]["archive_bytes"],
        "smart":smart,
        "flat":flat,
        "adaptive":{
            "layout":selected,
            "archive_bytes":chosen["archive_bytes"],
            "ratio":chosen["ratio"],
            "comp_time_s":chosen["comp_time_s"]+routing,
            "dec_time_s":chosen["dec_time_s"],
            "sha_ok":chosen["sha_ok"],
        },
        "flat_minus_smart_bytes":flat["archive_bytes"]-smart["archive_bytes"],
    }

Path("exp77_results.json").write_text(json.dumps(result,indent=2,sort_keys=True))
print("EXP77_RESULTS",json.dumps(result,sort_keys=True),flush=True)
