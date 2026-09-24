#!/usr/bin/env python3
"""
KSV-13 adaptive motion shortlist.

Uses a cheap sparse luma mean-absolute-difference classifier before MC8R4.
Low-motion inter frames search the first 9 ordered candidates; all other
frames keep the full 25-candidate search. Decoder syntax is unchanged because
the shortlist is a prefix of the canonical candidate order.
"""
import argparse, hashlib, json, shutil, subprocess, struct, time, zlib
from pathlib import Path
import numpy as np

from kstream_video_baseline import frame_sizes
from kstream_video_motion_control import spatial_frame, spatial_frame_inv, candidates, split_np, motion_inverse
from ksv12_motion_shortlist import limited_motion_residual

OUT=Path("results/video/ksv13_adaptive_shortlist")
W=176; H=144; GOP=10; BLOCK=8; RADIUS=4
MAGIC=b"KSA3"; VERSION=1
HDR=struct.Struct("<4sBBBHHII")  # magic,ver,block,radius,w,h,fpsn,fpsd
CHUNK=struct.Struct("<III")

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def sparse_luma_mad(frame,prev,w,h,step=8):
    y=np.frombuffer(frame,dtype=np.uint8,count=w*h).reshape(h,w)
    p=np.frombuffer(prev,dtype=np.uint8,count=w*h).reshape(h,w)
    a=y[::step,::step].astype(np.int16)
    b=p[::step,::step].astype(np.int16)
    return float(np.abs(a-b).mean())

def encode_file(src,dst,w,h,fpsn,fpsd,threshold):
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    if len(raw)%fs: raise ValueError("incomplete frames")
    total=len(raw)//fs
    low=0; inter=0; activity_sum=0.0
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,BLOCK,RADIUS,w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(GOP,total-off); payload=bytearray(); prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None:
                    payload.extend(spatial_frame(frame,w,h))
                else:
                    mad=sparse_luma_mad(frame,prev,w,h)
                    activity_sum+=mad; inter+=1
                    limit=9 if mad<=threshold else 25
                    if limit==9: low+=1
                    mv,res=limited_motion_residual(frame,prev,w,h,BLOCK,RADIUS,limit)
                    payload.extend(mv); payload.extend(res)
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n
    return {
        "low_motion_frames":low,
        "inter_frames":inter,
        "shortlist_percent":(100.0*low/inter if inter else 0.0),
        "mean_sparse_luma_mad":(activity_sum/inter if inter else 0.0)
    }

def decode_file(src,dst):
    b=src.read_bytes()
    magic,ver,block,radius,w,h,fpsn,fpsd=HDR.unpack_from(b,0)
    if magic!=MAGIC or ver!=VERSION: raise ValueError("bad header")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    mvn=(w//block)*(h//block)
    pos=HDR.size; out=bytearray()
    while pos<len(b):
        n,sz,crc=CHUNK.unpack_from(b,pos); pos+=CHUNK.size
        p=b[pos:pos+sz]; pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise ValueError("crc")
        q=0; prev=None
        for _ in range(n):
            if prev is None:
                frame=spatial_frame_inv(p[q:q+fs],w,h); q+=fs
            else:
                mv=p[q:q+mvn]; q+=mvn
                res=p[q:q+fs]; q+=fs
                frame=motion_inverse(mv,res,prev,w,h,block,radius)
            out.extend(frame); prev=frame
        if q!=len(p): raise ValueError("trailing chunk")
    dst.write_bytes(out)

def bench(src,name,fpsn,fpsd,exe,threshold):
    tag=f"{name}_T{threshold:g}"
    front=OUT/f"{tag}.front"; arc=OUT/f"{tag}.aur"
    dec=OUT/f"{tag}.dec"; od=OUT/f"{tag}_out"
    t=time.perf_counter()
    stats=encode_file(src,front,W,H,fpsn,fpsd,threshold)
    fe=time.perf_counter()-t
    ke=run([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"])
    if od.exists(): shutil.rmtree(od)
    run([str(exe.resolve()),"dp",str(arc),str(od),"6"])
    files=[p for p in od.rglob("*") if p.is_file()]
    if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI SHA FAIL")
    decode_file(front,dec)
    if sha(src)!=sha(dec): raise SystemExit("FRONTEND SHA FAIL")
    return {
        "threshold":threshold,
        "frontend_bytes":front.stat().st_size,
        "final_bytes":arc.stat().st_size,
        "encode_seconds":fe+ke,
        "sha_ok":True,
        **stats
    }

def parse(s):
    n,p,a,b=s.split(":")
    return n,Path(p).resolve(),int(a),int(b)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)

    # T0 approximates the full-search control except for exact-zero sampled changes.
    thresholds=(0.0,2.0,4.0,6.0)
    clips=[]
    for spec in a.clip:
        name,src,fpsn,fpsd=parse(spec)
        rows=[bench(src,name,fpsn,fpsd,a.kephir,t) for t in thresholds]
        base=rows[0]["final_bytes"]; bt=rows[0]["encode_seconds"]
        for r in rows:
            r["delta_vs_t0_bytes"]=r["final_bytes"]-base
            r["delta_vs_t0_percent"]=100.0*(r["final_bytes"]-base)/base
            r["speedup_vs_t0_x"]=bt/r["encode_seconds"]
        clips.append({"name":name,"rows":rows})
        print(clips[-1],flush=True)

    result={"experiment":"KSV-13 adaptive motion shortlist","clips":clips,
            "notes":["9 candidates used only when sparse luma MAD <= threshold.",
                     "Decoder bitstream semantics unchanged; all outputs SHA verified."]}
    (OUT/"KSV13_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
