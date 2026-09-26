#!/usr/bin/env python3
"""
EXP-103 — Grain Attribution Audit

Separates three effects behind the remaining mozilla gap:
1. native static factory policy;
2. Python exact per-parent probing from a fresh model;
3. Python session learning after dickens.

For mozilla it reconstructs the selected grain for every 512 KiB parent,
maps it to the canonical grain feature bucket, and attributes archive-size
differences parent-by-parent.
"""
from pathlib import Path
import collections
import copy
import json
import shutil
import struct
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K
E=K.E

CH=512*1024


def get_varint(data,pos):
    value=0; shift=0
    while True:
        b=data[pos]; pos+=1
        value |= (b & 0x7f) << shift
        if not (b & 0x80): return value,pos
        shift += 7


def extract_blob(path):
    data=path.read_bytes()
    assert data[:4]==b"KPF1" and data[4]==0
    pos=5
    n,pos=get_varint(data,pos); pos+=n
    bl,pos=get_varint(data,pos)
    blob=data[pos:pos+bl]; pos+=bl
    assert pos==len(data)
    return blob


def parse_k75(blob):
    assert blob[:4]==b"K75U"
    pos=4
    total=struct.unpack_from("<Q",blob,pos)[0]; pos+=8
    count=struct.unpack_from("<I",blob,pos)[0]; pos+=4
    entries=[]
    raw_off=0
    for i in range(count):
        mode=blob[pos]; pos+=1
        raw_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        comp_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        pos += comp_size
        entries.append({
            "index":i,
            "raw_offset":raw_off,
            "raw_size":raw_size,
            "mode":mode,
            "comp_size":comp_size,
            "stored_bytes":9+comp_size,
        })
        raw_off += raw_size
    assert raw_off==total and pos==len(blob)
    return entries


def fresh_model():
    return K.merge_models(K.load_factory(True),{})


def compress_python(src,dst,tmp,model):
    stats=K.compress_file(src,dst,model,tmp)
    return stats


def compress_native(cli,src,dst):
    subprocess.run(
        [str(cli),"c",str(src),str(dst),"1"],
        check=True,text=True,capture_output=True
    )


def parent_summaries(raw,entries):
    parents=[]
    ei=0
    for pidx,start in enumerate(range(0,len(raw),CH)):
        plen=min(CH,len(raw)-start)
        end=start+plen
        subset=[]
        cursor=start
        while ei<len(entries) and entries[ei]["raw_offset"] < end:
            e=entries[ei]
            assert e["raw_offset"]==cursor, (pidx,cursor,e)
            subset.append(e)
            cursor += e["raw_size"]
            ei += 1
        assert cursor==end, (pidx,cursor,end)
        grain=subset[0]["raw_size"] if subset else 0
        parents.append({
            "parent_index":pidx,
            "raw_offset":start,
            "raw_size":plen,
            "grain":grain,
            "entry_count":len(subset),
            "stored_bytes":sum(e["stored_bytes"] for e in subset),
            "modes":dict(collections.Counter(str(e["mode"]) for e in subset)),
            "bucket":E.grain_feature_bucket(raw[start:end]),
        })
    assert ei==len(entries)
    return parents


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp103_grain_attribution.py NATIVE_CLI")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp103_grain_attribution"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()

    dickens=corpus/"dickens"
    mozilla=corpus/"mozilla"
    raw=mozilla.read_bytes()

    # A — Python mozilla from a clean factory model.
    fresh=fresh_model()
    fresh_arc=work/"mozilla.python_fresh.kpf"
    fresh_stats=compress_python(
        mozilla,fresh_arc,work/"fresh_tmp",fresh
    )

    # B — exact EXP-91 ordering: train/use model on dickens first.
    session=fresh_model()
    dickens_arc=work/"dickens.session.kpf"
    compress_python(
        dickens,dickens_arc,work/"dickens_tmp",session
    )
    session_arc=work/"mozilla.python_after_dickens.kpf"
    session_stats=compress_python(
        mozilla,session_arc,work/"session_tmp",session
    )

    # C — current native.
    native_arc=work/"mozilla.native.kpf"
    compress_native(cli,mozilla,native_arc)

    variants={
        "python_fresh":{
            "archive":fresh_arc,
            "stats":fresh_stats,
        },
        "python_after_dickens":{
            "archive":session_arc,
            "stats":session_stats,
        },
        "native":{
            "archive":native_arc,
            "stats":None,
        },
    }

    for v in variants.values():
        v["archive_bytes"]=v["archive"].stat().st_size
        v["parents"]=parent_summaries(
            raw,parse_k75(extract_blob(v["archive"]))
        )

    base=variants["native"]["parents"]
    pf=variants["python_fresh"]["parents"]
    ps=variants["python_after_dickens"]["parents"]
    assert len(base)==len(pf)==len(ps)

    mismatches=[]
    by_bucket={}
    for n,f,s in zip(base,pf,ps):
        assert n["bucket"]==f["bucket"]==s["bucket"]
        row={
            "parent_index":n["parent_index"],
            "bucket":n["bucket"],
            "native_grain":n["grain"],
            "fresh_grain":f["grain"],
            "session_grain":s["grain"],
            "native_stored_bytes":n["stored_bytes"],
            "fresh_stored_bytes":f["stored_bytes"],
            "session_stored_bytes":s["stored_bytes"],
            "fresh_minus_native":f["stored_bytes"]-n["stored_bytes"],
            "session_minus_native":s["stored_bytes"]-n["stored_bytes"],
            "session_minus_fresh":s["stored_bytes"]-f["stored_bytes"],
        }
        if not (
            n["grain"]==f["grain"]==s["grain"]
            and n["stored_bytes"]==f["stored_bytes"]==s["stored_bytes"]
        ):
            mismatches.append(row)

        agg=by_bucket.setdefault(n["bucket"],{
            "parents":0,
            "native_bytes":0,
            "fresh_bytes":0,
            "session_bytes":0,
            "grain_triplets":collections.Counter(),
        })
        agg["parents"]+=1
        agg["native_bytes"]+=n["stored_bytes"]
        agg["fresh_bytes"]+=f["stored_bytes"]
        agg["session_bytes"]+=s["stored_bytes"]
        agg["grain_triplets"][
            f'{n["grain"]}/{f["grain"]}/{s["grain"]}'
        ] += 1

    for key,a in by_bucket.items():
        a["fresh_minus_native"]=a["fresh_bytes"]-a["native_bytes"]
        a["session_minus_native"]=a["session_bytes"]-a["native_bytes"]
        a["session_minus_fresh"]=a["session_bytes"]-a["fresh_bytes"]
        a["grain_triplets"]=dict(a["grain_triplets"])

    result={
        "experiment":"EXP-103",
        "mozilla_raw_bytes":len(raw),
        "archive_bytes":{
            k:v["archive_bytes"] for k,v in variants.items()
        },
        "archive_deltas":{
            "fresh_minus_native":
                variants["python_fresh"]["archive_bytes"]
                -variants["native"]["archive_bytes"],
            "session_minus_native":
                variants["python_after_dickens"]["archive_bytes"]
                -variants["native"]["archive_bytes"],
            "session_minus_fresh":
                variants["python_after_dickens"]["archive_bytes"]
                -variants["python_fresh"]["archive_bytes"],
        },
        "mismatching_parents":mismatches,
        "by_bucket":by_bucket,
        "python_fresh_stats":fresh_stats,
        "python_session_stats":session_stats,
    }

    Path("exp103_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True,default=str)
    )

    print(
        "EXP103_ARCHIVES",
        json.dumps(result["archive_bytes"],sort_keys=True),
        flush=True
    )
    print(
        "EXP103_DELTAS",
        json.dumps(result["archive_deltas"],sort_keys=True),
        flush=True
    )
    print("EXP103_MISMATCH_PARENTS",len(mismatches),flush=True)

    for row in sorted(
        mismatches,
        key=lambda r:abs(r["session_minus_native"]),
        reverse=True
    )[:40]:
        print("EXP103_PARENT",json.dumps(row,sort_keys=True),flush=True)

    for key,a in sorted(
        by_bucket.items(),
        key=lambda kv:abs(kv[1]["session_minus_native"]),
        reverse=True
    ):
        if a["fresh_minus_native"] or a["session_minus_native"]:
            print(
                "EXP103_BUCKET",key,
                json.dumps(a,sort_keys=True),
                flush=True
            )

    print("EXP103_AUDIT_COMPLETE",flush=True)


if __name__=="__main__":
    main()
