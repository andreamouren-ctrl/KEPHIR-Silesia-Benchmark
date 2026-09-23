#!/usr/bin/env python3
"""
KSV-12 motion shortlist regularization.

Same MC8R4 frontend, same residual representation, same EXP-37A backend.
Only the number of ordered motion candidates is limited to 25, 13, or 9.

Purpose: verify on natural diagnostic clips whether the strong 4K synthetic
speed/size result survives real content.
"""
import argparse, hashlib, json, shutil, subprocess, struct, time, zlib
from pathlib import Path
import numpy as np

from kstream_video_baseline import frame_sizes
from kstream_video_motion_control import spatial_frame, spatial_frame_inv, candidates, split_np, motion_inverse

OUT=Path("results/video/ksv12_motion_shortlist")
W=176; H=144; GOP=10; BLOCK=8; RADIUS=4
MAGIC=b"KSL2"; VERSION=1; HDR=struct.Struct("<4sBBBBHHII"); CHUNK=struct.Struct("<III")

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    t=time.perf_counter(); subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); return time.perf_counter()-t

def limited_motion_residual(frame,prev,w,h,block,radius,limit):
    cy,cu,cv=split_np(frame,w,h); py,pu,pv=split_np(prev,w,h)
    cand=candidates(radius)[:limit]
    mv=bytearray()
    ry=np.empty_like(cy); ru=np.empty_like(cu); rv=np.empty_like(cv)
    for y0 in range(0,h,block):
        for x0 in range(0,w,block):
            cur=cy[y0:y0+block,x0:x0+block].astype(np.int16)
            best_i=None; best_cost=None
            for i,(dx,dy) in enumerate(cand):
                sx=x0+dx; sy=y0+dy
                if sx<0 or sy<0 or sx+block>w or sy+block>h: continue
                ref=py[sy:sy+block,sx:sx+block].astype(np.int16)
                cost=int(np.abs(cur-ref).sum())
                if best_cost is None or cost<best_cost:
                    best_cost=cost; best_i=i
            if best_i is None: raise ValueError("no candidate")
            mv.append(best_i)
            dx,dy=cand[best_i]
            ref=py[y0+dy:y0+dy+block,x0+dx:x0+dx+block].astype(np.int16)
            ry[y0:y0+block,x0:x0+block]=((cur-ref)&255).astype(np.uint8)

            cb=block//2; cx=x0//2; cy0=y0//2; cdx=dx//2; cdy=dy//2
            ucur=cu[cy0:cy0+cb,cx:cx+cb].astype(np.int16)
            uref=pu[cy0+cdy:cy0+cdy+cb,cx+cdx:cx+cdx+cb].astype(np.int16)
            vcur=cv[cy0:cy0+cb,cx:cx+cb].astype(np.int16)
            vref=pv[cy0+cdy:cy0+cdy+cb,cx+cdx:cx+cdx+cb].astype(np.int16)
            ru[cy0:cy0+cb,cx:cx+cb]=((ucur-uref)&255).astype(np.uint8)
            rv[cy0:cy0+cb,cx:cx+cb]=((vcur-vref)&255).astype(np.uint8)
    return bytes(mv),ry.tobytes()+ru.tobytes()+rv.tobytes()

def encode_file(src,dst,w,h,fpsn,fpsd,limit):
    raw=src.read_bytes(); ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs; total=len(raw)//fs
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,BLOCK,RADIUS,limit,w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(GOP,total-off); payload=bytearray(); prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None: payload.extend(spatial_frame(frame,w,h))
                else:
                    mv,res=limited_motion_residual(frame,prev,w,h,BLOCK,RADIUS,limit)
                    payload.extend(mv); payload.extend(res)
                prev=frame
            p=bytes(payload); f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n

def decode_file(src,dst):
    b=src.read_bytes(); magic,ver,block,radius,limit,w,h,fpsn,fpsd=HDR.unpack_from(b,0)
    if magic!=MAGIC or ver!=VERSION: raise ValueError("bad header")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs; mvn=(w//block)*(h//block)
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
                mv=p[q:q+mvn]; q+=mvn; res=p[q:q+fs]; q+=fs
                # motion_inverse expects the full ordered candidate list and indexes remain valid
                # because shortlist uses the prefix of that same list.
                frame=motion_inverse(mv,res,prev,w,h,block,radius)
            out.extend(frame); prev=frame
    dst.write_bytes(out)

def bench(src,name,fpsn,fpsd,exe,limit):
    front=OUT/f"{name}_C{limit}.front"; arc=OUT/f"{name}_C{limit}.aur"; dec=OUT/f"{name}_C{limit}.dec"; od=OUT/f"{name}_C{limit}_out"
    t=time.perf_counter(); encode_file(src,front,W,H,fpsn,fpsd,limit); fe=time.perf_counter()-t
    ke=run([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"])
    if od.exists(): shutil.rmtree(od)
    run([str(exe.resolve()),"dp",str(arc),str(od),"6"])
    files=[p for p in od.rglob("*") if p.is_file()]
    if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI SHA FAIL")
    decode_file(front,dec)
    if sha(src)!=sha(dec): raise SystemExit("frontend SHA FAIL")
    return {"candidates":limit,"frontend_bytes":front.stat().st_size,"final_bytes":arc.stat().st_size,"encode_seconds":fe+ke,"sha_ok":True}

def parse(s):
    n,p,a,b=s.split(":"); return n,Path(p).resolve(),int(a),int(b)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--kephir",type=Path,required=True); ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    clips=[]
    for spec in a.clip:
        name,src,fpsn,fpsd=parse(spec)
        rows=[bench(src,name,fpsn,fpsd,a.kephir,c) for c in (25,13,9)]
        base=rows[0]["final_bytes"]
        for r in rows:
            r["delta_vs_25_bytes"]=r["final_bytes"]-base
            r["delta_vs_25_percent"]=100*(r["final_bytes"]-base)/base
        clips.append({"name":name,"rows":rows}); print(clips[-1],flush=True)
    result={"experiment":"KSV-12 motion shortlist regularization","clips":clips}
    (OUT/"KSV12_RESULTS.json").write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=="__main__": main()
