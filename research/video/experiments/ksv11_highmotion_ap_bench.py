#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, tempfile, time
from pathlib import Path

from ksv08_threeway_router import encode_candidate, MODE_TEMP, MODE_MC_MOD8, MODE_MC_ZZ, frame_size
from ksv09_mode_predictor import residual_stats
from kstream_video_adaptive_partition_v10 import encode_file as ap_encode

OUT=Path("results/video/ksv11_highmotion_ap")
THRESHOLDS=(5.5,6.5,7.5)

def run(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def kcp(exe,src,arc):
    return run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])

def parse(s):
    n,p,w,h,fpsn,fpsd,gop=s.split(":")
    return n,Path(p).resolve(),int(w),int(h),int(fpsn),int(fpsd),int(gop)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    ap.add_argument("--route-span",type=int,default=20)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)

    windows=[]
    with tempfile.TemporaryDirectory(prefix="ksv11_") as td:
        tmp=Path(td)
        for spec in a.clip:
            name,src,w,h,fpsn,fpsd,gop=parse(spec)
            raw=src.read_bytes(); fs=frame_size(w,h); total=len(raw)//fs
            for wi,off in enumerate(range(0,total,a.route_span)):
                n=min(a.route_span,total-off)
                chunk=raw[off*fs:(off+n)*fs]
                stats=residual_stats(chunk,w,h,8,4)
                mc_mode=MODE_MC_ZZ if stats["mean_signed_mag"]<2.60 else MODE_MC_MOD8

                temp,_=encode_candidate(chunk,MODE_TEMP,tmp,a.kephir,w,h,fpsn,fpsd,gop,wi*10+0)
                mc,_=encode_candidate(chunk,mc_mode,tmp,a.kephir,w,h,fpsn,fpsd,gop,wi*10+1)
                operational=min(len(temp),len(mc))

                rawp=tmp/f"{name}_{wi}.yuv"; front=tmp/f"{name}_{wi}.ap"; arc=tmp/f"{name}_{wi}.ap.aur"
                rawp.write_bytes(chunk)
                ap_encode(rawp,front,w,h,fpsn,fpsd,gop,4,256)
                kcp(a.kephir,front,arc)
                apbytes=arc.stat().st_size

                rec={"clip":name,"window":wi,"mean_signed_mag":stats["mean_signed_mag"],
                     "operational_bytes":operational,"ap256_bytes":apbytes,
                     "ap_delta_bytes":apbytes-operational}
                windows.append(rec); print(rec,flush=True)

    summary={}
    for t in THRESHOLDS:
        total=0; base=0; activated=0; wins=0
        for r in windows:
            base+=r["operational_bytes"]
            if r["mean_signed_mag"]>t:
                activated+=1
                chosen=min(r["operational_bytes"],r["ap256_bytes"])
                if r["ap256_bytes"]<r["operational_bytes"]: wins+=1
            else:
                chosen=r["operational_bytes"]
            total+=chosen
        summary[str(t)]={"bytes":total,"baseline_bytes":base,"delta_bytes":total-base,
                         "delta_percent":100*(total-base)/base,
                         "activated_windows":activated,"ap_wins":wins}
    result={"experiment":"KSV-11 high-motion AP256 gating","thresholds":summary,"windows":windows}
    (OUT/"KSV11_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
