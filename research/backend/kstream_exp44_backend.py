#!/usr/bin/env python3
"""
KHEPRI EXP-44 structural-router backend for arbitrary single-file payloads.

Research wrapper around EXP-37A. Each 512 KiB chunk is tested in three
reversible structural representations and the smallest resulting KHEPRI
archive is stored with its mode. Decoder is deterministic and bit-exact.
"""
import argparse, hashlib, shutil, struct, subprocess, tempfile
from pathlib import Path

MAGIC=b"K44S"
VERSION=1
CHUNK=512*1024
HDR=struct.Struct("<4sBQI")
ENT=struct.Struct("<BII")

def delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b-buf[i-lag])&255
    return bytes(out)

def inv_delta(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b+out[i-lag])&255
    return bytes(out)

def transpose(buf,w):
    rows=len(buf)//w; main=rows*w
    out=bytearray()
    for c in range(w):
        out.extend(buf[c:main:w])
    out.extend(buf[main:])
    return bytes(out)

def inv_transpose(buf,w,rawlen):
    rows=rawlen//w; main=rows*w
    out=bytearray(rawlen); k=0
    for c in range(w):
        for r in range(rows):
            out[r*w+c]=buf[k]; k+=1
    out[main:]=buf[k:]
    return bytes(out)

def transform(buf,mode):
    if mode==0: return buf
    if mode==1: return transpose(delta_lag(buf,4),4)
    if mode==2: return transpose(delta_lag(buf,1024),1024)
    raise ValueError("bad mode")

def inverse(buf,mode,rawlen):
    if mode==0: return buf
    if mode==1: return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2: return inv_delta(inv_transpose(buf,1024,rawlen),1024)
    raise ValueError("bad mode")

def _cp(exe:Path,payload:bytes,tmp:Path,tag:str):
    inp=tmp/f"{tag}.bin"; arc=tmp/f"{tag}.aur"
    inp.write_bytes(payload)
    subprocess.run([str(exe.resolve()),"cp",str(inp),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data=arc.read_bytes()
    inp.unlink(missing_ok=True); arc.unlink(missing_ok=True)
    return data

def _dp(exe:Path,payload:bytes,tmp:Path,tag:str):
    arc=tmp/f"{tag}.aur"; outdir=tmp/f"{tag}_out"
    arc.write_bytes(payload)
    if outdir.exists(): shutil.rmtree(outdir)
    subprocess.run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1: raise RuntimeError("unexpected EXP-37 decode output")
    data=files[0].read_bytes()
    arc.unlink(missing_ok=True); shutil.rmtree(outdir)
    return data

def encode_file(src:Path,dst:Path,exe:Path):
    raw=src.read_bytes()
    with tempfile.TemporaryDirectory(prefix="k44s_") as td:
        tmp=Path(td)
        entries=[]
        counts=[0,0,0]
        for idx,start in enumerate(range(0,len(raw),CHUNK)):
            chunk=raw[start:start+CHUNK]
            cand=[]
            for mode in (0,1,2):
                comp=_cp(exe,transform(chunk,mode),tmp,f"c{idx}_{mode}")
                cand.append((len(comp),mode,comp))
            _,mode,comp=min(cand,key=lambda x:(x[0],x[1]))
            counts[mode]+=1
            entries.append((mode,len(chunk),comp))
        with dst.open("wb") as f:
            f.write(HDR.pack(MAGIC,VERSION,len(raw),len(entries)))
            for mode,n,comp in entries:
                f.write(ENT.pack(mode,n,len(comp)))
                f.write(comp)
    return counts

def decode_file(src:Path,dst:Path,exe:Path):
    data=src.read_bytes(); pos=0
    if len(data)<HDR.size: raise ValueError("truncated header")
    magic,ver,total,count=HDR.unpack_from(data,pos); pos+=HDR.size
    if magic!=MAGIC or ver!=VERSION: raise ValueError("unsupported stream")
    out=bytearray()
    with tempfile.TemporaryDirectory(prefix="k44s_") as td:
        tmp=Path(td)
        for idx in range(count):
            if pos+ENT.size>len(data): raise ValueError("truncated entry")
            mode,n,cs=ENT.unpack_from(data,pos); pos+=ENT.size
            if mode not in (0,1,2) or pos+cs>len(data): raise ValueError("bad entry")
            comp=data[pos:pos+cs]; pos+=cs
            transformed=_dp(exe,comp,tmp,f"d{idx}")
            chunk=inverse(transformed,mode,n)
            if len(chunk)!=n: raise ValueError("decoded size mismatch")
            out.extend(chunk)
    if pos!=len(data) or len(out)!=total: raise ValueError("stream size mismatch")
    dst.write_bytes(out)

def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode"); e.add_argument("src",type=Path); e.add_argument("dst",type=Path); e.add_argument("--exe",type=Path,default=Path("./kephir37"))
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path); d.add_argument("--exe",type=Path,default=Path("./kephir37"))
    a=ap.parse_args()
    if a.cmd=="encode": print({"modes":encode_file(a.src,a.dst,a.exe)})
    else: decode_file(a.src,a.dst,a.exe)

if __name__=="__main__":
    main()
