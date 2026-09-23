#!/usr/bin/env python3
"""
KSV-09B two-encode router.

Per 20-frame window:
1. cheaply estimate MC residual signed magnitude;
2. choose MC_MOD8 or MC_ZZ_INTER with threshold 2.60;
3. run KHEPRI only for TEMP and the predicted MC candidate;
4. keep the smaller final payload.

This reduces backend trials from 3 to 2 per window.
"""
import argparse, hashlib, json, struct, tempfile
from pathlib import Path
from ksv08_threeway_router import (
    encode_candidate, decode_candidate, frame_size,
    MODE_TEMP, MODE_MC_MOD8, MODE_MC_ZZ, HDR, ENT, MAGIC, VERSION
)
from ksv09_mode_predictor import residual_stats

THRESHOLD=2.60

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def choose_mc(chunk,w,h):
    s=residual_stats(chunk,w,h,8,4)
    return (MODE_MC_ZZ if s["mean_signed_mag"]<THRESHOLD else MODE_MC_MOD8),s

def encode_file(src,dst,exe,w,h,fpsn,fpsd,gop=10,route_span=20):
    raw=src.read_bytes(); fs=frame_size(w,h)
    if len(raw)%fs: raise ValueError("incomplete frames")
    total=len(raw)//fs
    counts={0:0,1:0,2:0}; entries=[]; et=0.0; decisions=[]
    with tempfile.TemporaryDirectory(prefix="ksv09b_") as td:
        tmp=Path(td)
        for gi,off in enumerate(range(0,total,route_span)):
            n=min(route_span,total-off); chunk=raw[off*fs:(off+n)*fs]
            mc_mode,stats=choose_mc(chunk,w,h)
            temp,t1=encode_candidate(chunk,MODE_TEMP,tmp,exe,w,h,fpsn,fpsd,gop,gi*10)
            mc,t2=encode_candidate(chunk,mc_mode,tmp,exe,w,h,fpsn,fpsd,gop,gi*10+1)
            cand=[(len(temp),MODE_TEMP,temp,t1),(len(mc),mc_mode,mc,t2)]
            _,mode,payload,secs=min(cand,key=lambda x:(x[0],x[1]))
            counts[mode]+=1; et+=t1+t2; entries.append((mode,n,payload))
            decisions.append({"window":gi,"predicted_mc":"ZZ" if mc_mode==MODE_MC_ZZ else "MOD8",
                              "mean_signed_mag":stats["mean_signed_mag"],"selected_mode":mode})
        with dst.open("wb") as f:
            f.write(HDR.pack(MAGIC,VERSION,w,h,fpsn,fpsd,gop,route_span))
            for mode,n,payload in entries:
                f.write(ENT.pack(mode,n,len(payload))); f.write(payload)
    return counts,et,decisions

def decode_file(src,dst,exe):
    b=src.read_bytes(); pos=0
    magic,ver,w,h,fpsn,fpsd,gop,route_span=HDR.unpack_from(b,pos); pos+=HDR.size
    if magic!=MAGIC or ver!=VERSION: raise ValueError("bad stream")
    out=bytearray(); dt=0.0; idx=0
    with tempfile.TemporaryDirectory(prefix="ksv09bd_") as td:
        tmp=Path(td)
        while pos<len(b):
            mode,n,cs=ENT.unpack_from(b,pos); pos+=ENT.size
            payload=b[pos:pos+cs]; pos+=cs
            raw,secs=decode_candidate(payload,mode,tmp,exe,idx)
            if len(raw)!=n*frame_size(w,h): raise ValueError("decoded size")
            out.extend(raw); dt+=secs; idx+=1
    dst.write_bytes(out); return dt

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args()
    out=Path("results/video/ksv09b_twoencode"); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for spec in a.clip:
        name,p,w,h,fpsn,fpsd,gop=spec.split(":")
        src=Path(p).resolve(); w=int(w);h=int(h);fpsn=int(fpsn);fpsd=int(fpsd);gop=int(gop)
        arc=out/f"{name}.k9b"; dec=out/f"{name}.dec.yuv"
        counts,et,decisions=encode_file(src,arc,a.kephir,w,h,fpsn,fpsd,gop,20)
        dt=decode_file(arc,dec,a.kephir)
        if sha(src)!=sha(dec): raise SystemExit("SHA FAIL "+name)
        rows.append({"name":name,"bytes":arc.stat().st_size,"encode_seconds":et,"decode_seconds":dt,
                     "modes":{"TEMP":counts[0],"MC_MOD8":counts[1],"MC_ZZ":counts[2]},
                     "sha_ok":True,"decisions":decisions})
        print(rows[-1],flush=True)
    result={"experiment":"KSV-09B two-encode router","threshold":THRESHOLD,"rows":rows}
    (out/"KSV09B_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
