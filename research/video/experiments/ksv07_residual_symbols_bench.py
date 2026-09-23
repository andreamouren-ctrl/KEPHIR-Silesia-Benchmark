#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
from kstream_video_residual_symbols_v7 import encode_file, decode_file, MOD8, ZZ_INTER, ZZ_ALL

OUT=Path("results/video/ksv07_residual_symbols")
W=176; H=144; GOP=10; BLOCK=8; RADIUS=4
FS=W*H*3//2

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def bench_one(src,name,fpsn,fpsd,mode,label,exe):
    front=OUT/f"{name}_{label}.front"; dec=OUT/f"{name}_{label}.dec.yuv"
    arc=OUT/f"{name}_{label}.aur"; outdir=OUT/f"{name}_{label}_out"
    t=time.perf_counter()
    encode_file(src,front,W,H,fpsn,fpsd,GOP,BLOCK,RADIUS,mode)
    fe=time.perf_counter()-t
    t=time.perf_counter(); decode_file(front,dec,RADIUS); fd=time.perf_counter()-t
    if sha(src)!=sha(dec): raise SystemExit("frontend SHA FAIL")
    ke=run([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"])
    if outdir.exists(): shutil.rmtree(outdir)
    kd=run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"])
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI SHA FAIL")
    frames=src.stat().st_size//FS; dur=frames*fpsd/fpsn
    return dict(mode=label,frontend_bytes=front.stat().st_size,final_bytes=arc.stat().st_size,
                ratio_percent=100*arc.stat().st_size/src.stat().st_size,
                encode_seconds=fe+ke,decode_seconds=fd+kd,
                encode_realtime_x=dur/(fe+ke),decode_realtime_x=dur/(fd+kd),sha_ok=True)

def parse(s):
    n,p,a,b=s.split(":"); return n,Path(p).resolve(),int(a),int(b)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--clip",action="append",required=True)
    ap.add_argument("--kephir",type=Path,required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    clips=[]
    for spec in a.clip:
        name,src,fpsn,fpsd=parse(spec)
        rows=[
            bench_one(src,name,fpsn,fpsd,MOD8,"MOD8",a.kephir),
            bench_one(src,name,fpsn,fpsd,ZZ_INTER,"ZZ_INTER",a.kephir),
            bench_one(src,name,fpsn,fpsd,ZZ_ALL,"ZZ_ALL",a.kephir),
        ]
        base=rows[0]["final_bytes"]
        for r in rows:
            r["delta_vs_mod8_bytes"]=r["final_bytes"]-base
            r["delta_vs_mod8_percent"]=100*(r["final_bytes"]-base)/base
        clips.append(dict(name=name,raw_bytes=src.stat().st_size,rows=rows))
        print(clips[-1],flush=True)
    result={"experiment":"KSV-07 residual symbol mapping","clips":clips}
    (OUT/"KSV07_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
