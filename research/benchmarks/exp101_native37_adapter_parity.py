#!/usr/bin/env python3
"""
EXP-101 — Native37 Adapter vs Legacy CLI Parity

Compares identical payloads through:
1. legacy ./kephir37 cp <input> <archive> 6 6.55 9.42 1.20
2. native kephir2_native37_blob_cli

Payloads include raw and tokenized text derived from Silesia so the audit
targets the exact area responsible for the remaining K75 ratio gap.
"""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys

ROOT=Path.cwd()
TOKENS=[
    b" the ",b" and ",b"ing",b"tion",b" of ",b" to ",b" in ",b" that ",
    b" is ",b" for ",b"ed ",b"er ",b"re ",b"en ",b"on ",b"at ",
    b"\n",b"</",b"/>",b"http",b"www.",b'="',b"<!--",b"-->",
    b"data",b"this",b"with",b"from",b"have",b"not ",b" as ",b" by "
]
SORTED=sorted(enumerate(TOKENS,1),key=lambda kv:len(kv[1]),reverse=True)
INDEX={}
for tid,tok in SORTED:
    INDEX.setdefault(tok[0],[]).append((tid,tok))

def tokenize(buf):
    out=bytearray(); i=0
    while i<len(buf):
        b=buf[i]; matched=False
        for tid,tok in INDEX.get(b,()):
            if buf.startswith(tok,i):
                out.extend((255,tid)); i+=len(tok); matched=True; break
        if matched:
            continue
        if b==255: out.extend((255,0))
        else: out.append(b)
        i+=1
    return bytes(out)

def parse_aur2(path):
    data=path.read_bytes()
    if data[:4] != b"AUR2":
        raise ValueError("not AUR2")
    pos=4
    version=struct.unpack_from("<I",data,pos)[0]; pos+=4
    entries=struct.unpack_from("<I",data,pos)[0]; pos+=4
    total_raw=struct.unpack_from("<Q",data,pos)[0]; pos+=8
    chunks=struct.unpack_from("<I",data,pos)[0]; pos+=4
    if entries != 1:
        raise ValueError("unexpected entries")
    n=struct.unpack_from("<I",data,pos)[0]; pos+=4+n
    entry_raw=struct.unpack_from("<Q",data,pos)[0]; pos+=8
    out=[]
    for i in range(chunks):
        raw=struct.unpack_from("<I",data,pos)[0]; pos+=4
        comp=struct.unpack_from("<I",data,pos)[0]; pos+=4
        payload=data[pos:pos+comp]; pos+=comp
        out.append({
            "index":i,
            "raw_size":raw,
            "comp_size":comp,
            "payload_sha256":__import__("hashlib").sha256(payload).hexdigest(),
        })
    if pos != len(data):
        raise ValueError("trailing bytes")
    return {
        "version":version,
        "total_raw":total_raw,
        "entry_raw":entry_raw,
        "archive_bytes":len(data),
        "chunks":out,
    }

def run_case(name,payload,native_cli,work):
    src=work/f"{name}.bin"
    legacy=work/f"{name}.legacy.aur"
    native=work/f"{name}.native.aur"
    src.write_bytes(payload)

    subprocess.run(
        ["./kephir37","cp",str(src),str(legacy),"6","6.55","9.42","1.20"],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL
    )
    subprocess.run(
        [str(native_cli),str(src),str(native)],
        check=True,text=True,capture_output=True
    )

    l=parse_aur2(legacy)
    n=parse_aur2(native)
    same_chunks=[
        lc["raw_size"]==nc["raw_size"]
        and lc["comp_size"]==nc["comp_size"]
        and lc["payload_sha256"]==nc["payload_sha256"]
        for lc,nc in zip(l["chunks"],n["chunks"])
    ]

    row={
        "name":name,
        "payload_bytes":len(payload),
        "legacy_archive_bytes":l["archive_bytes"],
        "native_archive_bytes":n["archive_bytes"],
        "delta_native_minus_legacy":
            n["archive_bytes"]-l["archive_bytes"],
        "legacy_chunks":l["chunks"],
        "native_chunks":n["chunks"],
        "same_chunk_count":len(l["chunks"])==len(n["chunks"]),
        "identical_chunk_payloads":
            len(l["chunks"])==len(n["chunks"]) and all(same_chunks),
    }
    print(
        "EXP101_CASE",name,
        "RAW",len(payload),
        "LEGACY",l["archive_bytes"],
        "NATIVE",n["archive_bytes"],
        "DELTA",row["delta_native_minus_legacy"],
        "IDENTICAL",row["identical_chunk_payloads"],
        flush=True,
    )
    return row

def main():
    if len(sys.argv)!=2:
        raise SystemExit(
            "usage: exp101_native37_adapter_parity.py "
            "/path/to/kephir2_native37_blob_cli"
        )

    native_cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp101_native37_parity"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    cases=[]
    for filename in ("dickens","webster","mozilla"):
        raw=(corpus/filename).read_bytes()
        first=raw[:512*1024]
        cases.append((filename+"_raw512",first))
        cases.append((filename+"_token512",tokenize(first)))

    rows=[run_case(name,payload,native_cli,work) for name,payload in cases]

    result={
        "experiment":"EXP-101",
        "rows":rows,
        "all_identical":all(r["identical_chunk_payloads"] for r in rows),
    }
    Path("exp101_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print(
        "EXP101_ALL_IDENTICAL",
        result["all_identical"],
        flush=True
    )

if __name__=="__main__":
    main()
