#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
from kstream_video_baseline import encode_file, decode_file

OUT=Path("streaming/ksv02_out")
W=176; H=144; GOP=10
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

def temporal(exe,raw,name,fpsn,fpsd):
    front=OUT/f"{name}_temporal.front"; restored=OUT/f"{name}_temporal.raw"
    t=time.perf_counter(); encode_file(raw,front,W,H,fpsn,fpsd,GOP,3); fe=time.perf_counter()-t
    t=time.perf_counter(); decode_file(front,restored); fd=time.perf_counter()-t
    if sha(restored)!=sha(raw): raise SystemExit(f"FRONT SHA FAIL {name}")
    kb,ke,kd=kephir(exe,front,f"{name}_TEMPORAL")
    return dict(codec="TEMPORAL_GOP10_PLUS_EXP33H",bytes=kb,frontend_bytes=front.stat().st_size,
                encode_seconds=fe+ke,decode_seconds=fd+kd,sha_ok=True)

def ffv1(raw,name,fpsn,fpsd):
    out=OUT/f"{name}.ffv1.mkv"; dec=OUT/f"{name}.ffv1.raw"
    for p in (out,dec):
        if p.exists(): p.unlink()
    common=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}","-r",f"{fpsn}/{fpsd}","-i",str(raw)]
    ce=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*common,
              "-c:v","ffv1","-level","3","-coder","1","-context","1","-g",str(GOP),str(out)])
    cd=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),
              "-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    if sha(dec)!=sha(raw): raise SystemExit(f"FFV1 SHA FAIL {name}")
    return dict(codec="FFV1_LEVEL3_GOP10",bytes=out.stat().st_size,
                encode_seconds=ce,decode_seconds=cd,sha_ok=True)

def parse_clip(s):
    # name:path:fps_num:fps_den
    name,path,fpsn,fpsd=s.split(":",3)
    return name,Path(path).resolve(),int(fpsn),int(fpsd)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",default="./kephir33")
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)

    clips=[]
    for spec in a.clip:
        name,raw,fpsn,fpsd=parse_clip(spec)
        raw_bytes=raw.stat().st_size
        if raw_bytes%FRAME_BYTES: raise SystemExit(f"bad raw video {name}")
        frames=raw_bytes//FRAME_BYTES
        duration=frames*fpsd/fpsn

        db,dce,dcd=kephir(a.kephir,raw,f"{name}_DIRECT")
        rows=[
            dict(codec="DIRECT_EXP33H",bytes=db,encode_seconds=dce,decode_seconds=dcd,sha_ok=True),
            temporal(a.kephir,raw,name,fpsn,fpsd),
            ffv1(raw,name,fpsn,fpsd),
        ]
        for r in rows:
            r["ratio_to_raw_percent"]=100*r["bytes"]/raw_bytes
            r["bits_per_pixel"]=8*r["bytes"]/(W*H*frames)
            r["encode_realtime_x"]=duration/r["encode_seconds"]
            r["decode_realtime_x"]=duration/r["decode_seconds"]

        t=rows[1]["bytes"]; f=rows[2]["bytes"]
        clips.append(dict(name=name,width=W,height=H,frames=frames,fps=f"{fpsn}/{fpsd}",
                          raw_bytes=raw_bytes,sha256=sha(raw),rows=rows,
                          temporal_delta_vs_ffv1_percent=100*(t-f)/f))

    result=dict(experiment="KS-V02 multi-motion generalization",
                gop=GOP,clips=clips,
                rule="Background controls only. No proprietary/patentability claim is made from temporal prediction itself.")
    (OUT/"ksv02_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()

# KSV02_TRIGGER_2
