#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
from kstream_video_adaptive_partition_v10 import encode_file as ap_encode, decode_file as ap_decode
from kstream_video_motion_control import encode_file as mc_encode, decode_file as mc_decode

OUT=Path("results/video/ksv10_adaptive_partition")
W=176; H=144; GOP=10; RADIUS=4

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t
def kcp(exe,src,arc):
    return run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
def kdp(exe,arc,outdir):
    if outdir.exists(): shutil.rmtree(outdir)
    return run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"])

def encode_khepri(src,front,arc,outdir,exe,kind,penalty=None):
    t=time.perf_counter()
    if kind=="MC8":
        mc_encode(src,front,W,H,30000,1001,GOP,8,RADIUS)
    else:
        ap_encode(src,front,W,H,30000,1001,GOP,RADIUS,penalty)
    fe=time.perf_counter()-t
    ke=kcp(exe,front,arc)
    kd=kdp(exe,arc,outdir)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI SHA FAIL")
    return fe+ke,kd

def bench(src,name,fpsn,fpsd,exe):
    rows=[]
    # baseline
    front=OUT/f"{name}_MC8.front"; arc=OUT/f"{name}_MC8.aur"; od=OUT/f"{name}_MC8_out"; dec=OUT/f"{name}_MC8.dec"
    t=time.perf_counter(); mc_encode(src,front,W,H,fpsn,fpsd,GOP,8,RADIUS); fe=time.perf_counter()-t
    tke=kcp(exe,front,arc); kdp(exe,arc,od)
    files=[p for p in od.rglob("*") if p.is_file()]
    if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI baseline SHA")
    t=time.perf_counter(); mc_decode(front,dec); fd=time.perf_counter()-t
    if sha(src)!=sha(dec): raise SystemExit("MC8 roundtrip")
    rows.append({"mode":"MC8R4","final_bytes":arc.stat().st_size,"frontend_bytes":front.stat().st_size,
                 "encode_seconds":fe+tke,"decode_seconds":fd,"sha_ok":True})

    for penalty in (0,256,1024):
        label=f"AP{penalty}"
        front=OUT/f"{name}_{label}.front"; arc=OUT/f"{name}_{label}.aur"; od=OUT/f"{name}_{label}_out"; dec=OUT/f"{name}_{label}.dec"
        t=time.perf_counter(); ap_encode(src,front,W,H,fpsn,fpsd,GOP,RADIUS,penalty); fe=time.perf_counter()-t
        tke=kcp(exe,front,arc); kdp(exe,arc,od)
        files=[p for p in od.rglob("*") if p.is_file()]
        if len(files)!=1 or sha(files[0])!=sha(front): raise SystemExit("KHEPRI adaptive SHA")
        t=time.perf_counter(); ap_decode(front,dec,GOP); fd=time.perf_counter()-t
        if sha(src)!=sha(dec): raise SystemExit("adaptive roundtrip")
        rows.append({"mode":label,"final_bytes":arc.stat().st_size,"frontend_bytes":front.stat().st_size,
                     "encode_seconds":fe+tke,"decode_seconds":fd,"sha_ok":True})
    base=rows[0]["final_bytes"]
    for r in rows:
        r["delta_vs_mc8_bytes"]=r["final_bytes"]-base
        r["delta_vs_mc8_percent"]=100*(r["final_bytes"]-base)/base
    return rows

def parse(s):
    n,p,a,b=s.split(":"); return n,Path(p).resolve(),int(a),int(b)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--kephir",type=Path,required=True); ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    clips=[]
    for spec in a.clip:
        name,src,fpsn,fpsd=parse(spec)
        rows=bench(src,name,fpsn,fpsd,a.kephir)
        clips.append({"name":name,"raw_bytes":src.stat().st_size,"rows":rows})
        print(clips[-1],flush=True)
    result={"experiment":"KSV-10 adaptive 16x16/8x8 partition","clips":clips}
    (OUT/"KSV10_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
