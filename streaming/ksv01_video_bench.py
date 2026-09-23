#!/usr/bin/env python3
import hashlib, json, shutil, subprocess, time
from pathlib import Path
from kstream_video_baseline import encode_file, decode_file

OUT=Path("streaming/ksv01_out")
W=176; H=144; FPSN=30000; FPSD=1001; GOP=10
FRAME_BYTES=W*H + 2*((W+1)//2)*((H+1)//2)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def kephir(exe,src,tag):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    ce=timed([str(Path(exe).resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    cd=timed([str(Path(exe).resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/Path(src).name
    if sha(restored)!=sha(src): raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size,ce,cd

def transformed(exe,raw,tag,mode):
    front=OUT/f"{tag}.front"; restored=OUT/f"{tag}.raw"
    t=time.perf_counter()
    encode_file(raw,front,W,H,FPSN,FPSD,GOP,mode)
    fe=time.perf_counter()-t
    t=time.perf_counter()
    decode_file(front,restored)
    fd=time.perf_counter()-t
    if sha(restored)!=sha(raw): raise SystemExit(f"FRONT SHA FAIL {tag}")
    kb,ke,kd=kephir(exe,front,tag)
    return dict(codec=tag,frontend_bytes=front.stat().st_size,bytes=kb,
                encode_seconds=fe+ke,decode_seconds=fd+kd,
                frontend_encode_seconds=fe,frontend_decode_seconds=fd,
                backend_encode_seconds=ke,backend_decode_seconds=kd,sha_ok=True)

def ffv1(raw):
    out=OUT/"ffv1.mkv"; dec=OUT/"ffv1.raw"
    if out.exists(): out.unlink()
    if dec.exists(): dec.unlink()
    common=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}","-r",f"{FPSN}/{FPSD}","-i",str(raw)]
    ce=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*common,
              "-c:v","ffv1","-level","3","-coder","1","-context","1","-g",str(GOP),str(out)])
    cd=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),
              "-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    if sha(dec)!=sha(raw): raise SystemExit("FFV1 SHA FAIL")
    return dict(codec="FFV1_LEVEL3_GOP10",bytes=out.stat().st_size,
                encode_seconds=ce,decode_seconds=cd,sha_ok=True)

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--raw",type=Path,required=True);ap.add_argument("--kephir",default="./kephir33")
    a=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); raw_bytes=raw.stat().st_size
    if raw_bytes%FRAME_BYTES: raise SystemExit("bad raw video")
    frames=raw_bytes//FRAME_BYTES; duration=frames*FPSD/FPSN

    direct_b,dce,dcd=kephir(a.kephir,raw,"DIRECT_YUV")
    rows=[
      dict(codec="DIRECT_KEPHIR_EXP33H",bytes=direct_b,encode_seconds=dce,decode_seconds=dcd,sha_ok=True),
      transformed(a.kephir,raw,"KSV_LEFT",1),
      transformed(a.kephir,raw,"KSV_PAETH",2),
      transformed(a.kephir,raw,"KSV_TEMPORAL_GOP10",3),
      ffv1(raw),
    ]
    for r in rows:
        r["ratio_to_raw_percent"]=100*r["bytes"]/raw_bytes
        r["bits_per_pixel"]=8*r["bytes"]/(W*H*frames)
        r["encode_realtime_x"]=duration/r["encode_seconds"]
        r["decode_realtime_x"]=duration/r["decode_seconds"]

    result=dict(experiment="KS-V01 reversible YUV420p video baseline",
                source=dict(width=W,height=H,frames=frames,fps=f"{FPSN}/{FPSD}",
                            bytes=raw_bytes,sha256=sha(raw),origin="Xiph Derf akiyo QCIF"),
                gop=GOP,rows=rows,
                rule="All KSV predictors are background controls. No candidate-IP claim is made from KS-V01.")
    (OUT/"ksv01_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
