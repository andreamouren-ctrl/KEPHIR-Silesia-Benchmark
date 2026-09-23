#!/usr/bin/env python3
import argparse, json, tempfile
from pathlib import Path

from ksv08_threeway_router import encode_candidate, MODE_TEMP, MODE_MC_MOD8, MODE_MC_ZZ, frame_size
from ksv09_mode_predictor import residual_stats

OUT=Path("results/video/ksv09_predictor")

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
    with tempfile.TemporaryDirectory(prefix="ksv09_") as td:
        tmp=Path(td)
        for spec in a.clip:
            name,src,w,h,fpsn,fpsd,gop=parse(spec)
            raw=src.read_bytes(); fs=frame_size(w,h); total=len(raw)//fs
            for wi,off in enumerate(range(0,total,a.route_span)):
                n=min(a.route_span,total-off)
                chunk=raw[off*fs:(off+n)*fs]
                temp,_=encode_candidate(chunk,MODE_TEMP,tmp,a.kephir,w,h,fpsn,fpsd,gop,wi*10+0)
                mod,_=encode_candidate(chunk,MODE_MC_MOD8,tmp,a.kephir,w,h,fpsn,fpsd,gop,wi*10+1)
                zz,_=encode_candidate(chunk,MODE_MC_ZZ,tmp,a.kephir,w,h,fpsn,fpsd,gop,wi*10+2)
                mc_oracle="ZZ" if len(zz)<len(mod) else "MOD8"
                full=min((len(temp),"TEMP"),(len(mod),"MOD8"),(len(zz),"ZZ"))
                rec={
                    "clip":name,"window":wi,"frames":n,
                    "temp_bytes":len(temp),"mc_mod8_bytes":len(mod),"mc_zz_bytes":len(zz),
                    "oracle_mc_mode":mc_oracle,"oracle_full_mode":full[1],
                    "stats":residual_stats(chunk,w,h,8,4)
                }
                windows.append(rec)
                print(rec,flush=True)
    result={"experiment":"KSV-09 window collector","route_span":a.route_span,"windows":windows}
    p=OUT/"windows.json"; p.write_text(json.dumps(result,indent=2))
    print(json.dumps({"windows":len(windows),"output":str(p)},indent=2))

if __name__=="__main__":main()
