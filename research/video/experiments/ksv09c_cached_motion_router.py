#!/usr/bin/env python3
"""
KSV-09C cached-motion two-encode router.

Improves KSV-09B by computing MC8R4 motion/residual once per routing window,
using the same cached residuals both for the mode predictor and for final
serialization. KHEPRI is invoked only for TEMP and one MC candidate.

Stream remains compatible with KSV-08 outer mode framing.
"""
import argparse, hashlib, json, shutil, struct, subprocess, tempfile, time, zlib
from pathlib import Path

from kstream_video_baseline import encode_file as temp_encode
from kstream_video_motion_control import (
    spatial_frame, motion_residual, frame_sizes,
    MAGIC as MC_MAGIC, VERSION as MC_VERSION, FMT_YUV420P8 as MC_FMT,
    HDR as MC_HDR, CHUNK as MC_CHUNK
)
from kstream_video_residual_symbols_v7 import (
    map_residual, ZZ_INTER,
    MAGIC as ZZ_MAGIC, VERSION as ZZ_VERSION, FMT_YUV420P8 as ZZ_FMT,
    HDR as ZZ_HDR, CHUNK as ZZ_CHUNK
)
from ksv08_threeway_router import (
    decode_file as decode_router, frame_size,
    MODE_TEMP, MODE_MC_MOD8, MODE_MC_ZZ, HDR, ENT, MAGIC, VERSION
)

THRESHOLD=2.60
BLOCK=8
RADIUS=4

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def kcp(exe,src,arc):
    return run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])

def build_cached_mc_front(raw_chunk,w,h,fpsn,fpsd,gop):
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    total=len(raw_chunk)//fs
    chunks=[]
    magsum=0
    magcount=0

    off=0
    while off<total:
        n=min(gop,total-off)
        frame_records=[]
        prev=None
        for j in range(n):
            frame=raw_chunk[(off+j)*fs:(off+j+1)*fs]
            if prev is None:
                intra=spatial_frame(frame,w,h)
                frame_records.append(("I",intra))
            else:
                mv,res=motion_residual(frame,prev,w,h,BLOCK,RADIUS)
                magsum += sum((b if b<128 else 256-b) for b in res)
                magcount += len(res)
                frame_records.append(("P",mv,res))
            prev=frame
        chunks.append((n,frame_records))
        off+=n

    mean_mag=(magsum/magcount) if magcount else 0.0
    mode=MODE_MC_ZZ if mean_mag<THRESHOLD else MODE_MC_MOD8

    out=bytearray()
    if mode==MODE_MC_MOD8:
        out.extend(MC_HDR.pack(MC_MAGIC,MC_VERSION,MC_FMT,gop,BLOCK,RADIUS,w,h,fpsn,fpsd))
        for n,recs in chunks:
            payload=bytearray()
            for rec in recs:
                if rec[0]=="I": payload.extend(rec[1])
                else:
                    payload.extend(rec[1]); payload.extend(rec[2])
            p=bytes(payload)
            out.extend(MC_CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); out.extend(p)
    else:
        out.extend(ZZ_HDR.pack(ZZ_MAGIC,ZZ_VERSION,ZZ_FMT,gop,BLOCK,ZZ_INTER,w,h,fpsn,fpsd))
        for n,recs in chunks:
            payload=bytearray()
            for rec in recs:
                if rec[0]=="I": payload.extend(rec[1])
                else:
                    payload.extend(rec[1]); payload.extend(map_residual(rec[2],ZZ_INTER))
            p=bytes(payload)
            out.extend(ZZ_CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); out.extend(p)

    return mode,mean_mag,bytes(out)

def encode_file(src,dst,exe,w,h,fpsn,fpsd,gop=10,route_span=20):
    raw=src.read_bytes(); fs=frame_size(w,h)
    total=len(raw)//fs
    counts={0:0,1:0,2:0}; entries=[]; encode_time=0.0; decisions=[]

    with tempfile.TemporaryDirectory(prefix="ksv09c_") as td:
        tmp=Path(td)
        for gi,off in enumerate(range(0,total,route_span)):
            n=min(route_span,total-off)
            chunk=raw[off*fs:(off+n)*fs]

            src_tmp=tmp/f"w{gi}.yuv"; src_tmp.write_bytes(chunk)

            # TEMP candidate.
            temp_front=tmp/f"w{gi}_temp.front"; temp_arc=tmp/f"w{gi}_temp.aur"
            t=time.perf_counter()
            temp_encode(src_tmp,temp_front,w,h,fpsn,fpsd,gop,3)
            temp_front_time=time.perf_counter()-t
            temp_k=kcp(exe,temp_front,temp_arc)
            temp_payload=temp_arc.read_bytes()

            # One MC search, reused for predictor + serialization.
            t=time.perf_counter()
            mc_mode,mean_mag,mc_front_bytes=build_cached_mc_front(chunk,w,h,fpsn,fpsd,gop)
            mc_front_time=time.perf_counter()-t
            mc_front=tmp/f"w{gi}_mc.front"; mc_arc=tmp/f"w{gi}_mc.aur"
            mc_front.write_bytes(mc_front_bytes)
            mc_k=kcp(exe,mc_front,mc_arc)
            mc_payload=mc_arc.read_bytes()

            candidates=[
                (len(temp_payload),MODE_TEMP,temp_payload),
                (len(mc_payload),mc_mode,mc_payload)
            ]
            _,mode,payload=min(candidates,key=lambda x:(x[0],x[1]))
            counts[mode]+=1
            encode_time += temp_front_time+temp_k+mc_front_time+mc_k
            entries.append((mode,n,payload))
            decisions.append({"window":gi,"mean_signed_mag":mean_mag,
                              "predicted_mc":"ZZ" if mc_mode==MODE_MC_ZZ else "MOD8",
                              "selected_mode":mode})

        with dst.open("wb") as f:
            f.write(HDR.pack(MAGIC,VERSION,w,h,fpsn,fpsd,gop,route_span))
            for mode,n,payload in entries:
                f.write(ENT.pack(mode,n,len(payload))); f.write(payload)

    return counts,encode_time,decisions

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args()
    out=Path("results/video/ksv09c_cached"); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for spec in a.clip:
        name,p,w,h,fpsn,fpsd,gop=spec.split(":")
        src=Path(p).resolve(); w=int(w);h=int(h);fpsn=int(fpsn);fpsd=int(fpsd);gop=int(gop)
        arc=out/f"{name}.k9c"; dec=out/f"{name}.dec.yuv"
        counts,et,decisions=encode_file(src,arc,a.kephir,w,h,fpsn,fpsd,gop,20)
        t=time.perf_counter(); decode_router(arc,dec,a.kephir); dt=time.perf_counter()-t
        if sha(src)!=sha(dec): raise SystemExit("SHA FAIL "+name)
        row={"name":name,"bytes":arc.stat().st_size,"encode_seconds":et,"decode_seconds":dt,
             "modes":{"TEMP":counts[0],"MC_MOD8":counts[1],"MC_ZZ":counts[2]},
             "sha_ok":True,"decisions":decisions}
        rows.append(row); print(row,flush=True)

    result={"experiment":"KSV-09C cached-motion router","threshold":THRESHOLD,"rows":rows}
    (out/"KSV09C_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
