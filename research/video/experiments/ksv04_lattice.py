#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path

from kstream_video_mc import encode_file as mc_encode, decode_file as mc_decode
from kstream_video_lattice import encode_file as lattice_encode, decode_file as lattice_decode

OUT=Path("streaming/ksv04_out")
W=176
H=144
GOP=10
RADIUS=4
FRAME_BYTES=W*H + 2*((W+1)//2)*((H+1)//2)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t


def kephir(exe,src,tag):
    arc=OUT/f"{tag}.aur"
    dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    ce=timed([str(Path(exe).resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    cd=timed([str(Path(exe).resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/Path(src).name
    if sha(restored)!=sha(src):
        raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size,ce,cd


def transformed(exe,raw,name,fpsn,fpsd,block,lattice):
    kind="LATTICE" if lattice else "RASTER"
    tag=f"{name}_MC{block}_R4_{kind}"
    front=OUT/f"{tag}.front"
    restored=OUT/f"{tag}.raw"
    enc=lattice_encode if lattice else mc_encode
    dec=lattice_decode if lattice else mc_decode

    t=time.perf_counter()
    enc(raw,front,W,H,fpsn,fpsd,GOP,block,RADIUS)
    fe=time.perf_counter()-t

    t=time.perf_counter()
    dec(front,restored)
    fd=time.perf_counter()-t
    if sha(restored)!=sha(raw):
        raise SystemExit(f"FRONT SHA FAIL {tag}")

    kb,ke,kd=kephir(exe,front,tag)
    return dict(
        codec=f"MC{block}_R4_{kind}",
        bytes=kb,
        frontend_bytes=front.stat().st_size,
        encode_seconds=fe+ke,
        decode_seconds=fd+kd,
        frontend_encode_seconds=fe,
        frontend_decode_seconds=fd,
        backend_encode_seconds=ke,
        backend_decode_seconds=kd,
        sha_ok=True,
    )


def ffv1(raw,name,fpsn,fpsd):
    out=OUT/f"{name}.ffv1.mkv"
    dec=OUT/f"{name}.ffv1.raw"
    for p in (out,dec):
        if p.exists(): p.unlink()
    common=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}",
            "-r",f"{fpsn}/{fpsd}","-i",str(raw)]
    ce=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*common,
              "-c:v","ffv1","-level","3","-coder","1","-context","1",
              "-g",str(GOP),str(out)])
    cd=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),
              "-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    if sha(dec)!=sha(raw):
        raise SystemExit(f"FFV1 SHA FAIL {name}")
    return dict(codec="FFV1_LEVEL3_GOP10",bytes=out.stat().st_size,
                encode_seconds=ce,decode_seconds=cd,sha_ok=True)


def parse_clip(s):
    name,path,fpsn,fpsd=s.split(":",3)
    return name,Path(path).resolve(),int(fpsn),int(fpsd)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",default="./kephir33")
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)

    clips=[]
    for spec in a.clip:
        name,raw,fpsn,fpsd=parse_clip(spec)
        raw_bytes=raw.stat().st_size
        if raw_bytes%FRAME_BYTES:
            raise SystemExit(f"bad raw video {name}")
        frames=raw_bytes//FRAME_BYTES
        duration=frames*fpsd/fpsn

        rows=[
            transformed(a.kephir,raw,name,fpsn,fpsd,16,False),
            transformed(a.kephir,raw,name,fpsn,fpsd,16,True),
            transformed(a.kephir,raw,name,fpsn,fpsd,8,False),
            transformed(a.kephir,raw,name,fpsn,fpsd,8,True),
            ffv1(raw,name,fpsn,fpsd),
        ]
        ff=rows[-1]["bytes"]
        raster16=rows[0]["bytes"]
        raster8=rows[2]["bytes"]
        for r in rows:
            r["ratio_to_raw_percent"]=100*r["bytes"]/raw_bytes
            r["bits_per_pixel"]=8*r["bytes"]/(W*H*frames)
            r["delta_vs_ffv1_percent"]=100*(r["bytes"]-ff)/ff
            r["encode_realtime_x"]=duration/r["encode_seconds"]
            r["decode_realtime_x"]=duration/r["decode_seconds"]
            if r["codec"]=="MC16_R4_LATTICE":
                r["delta_vs_matching_raster_percent"]=100*(r["bytes"]-raster16)/raster16
            elif r["codec"]=="MC8_R4_LATTICE":
                r["delta_vs_matching_raster_percent"]=100*(r["bytes"]-raster8)/raster8

        clips.append(dict(name=name,frames=frames,fps=f"{fpsn}/{fpsd}",
                          raw_bytes=raw_bytes,sha256=sha(raw),rows=rows))

    result=dict(
        experiment="KS-V04 block-major residual lattice control",
        gop=GOP,
        radius=RADIUS,
        clips=clips,
        hypothesis="Contiguous residual blocks expose recurrence at byte distances aligned with KHEPRI EXP-33H topology.",
        rule="Fixed block/raster reordering is BACKGROUND. A technical win is not by itself a patentability claim.",
    )
    (OUT/"ksv04_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
