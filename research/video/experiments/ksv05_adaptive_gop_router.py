#!/usr/bin/env python3
"""
KSV-05 Adaptive GOP Router.

Original AURORA project implementation.
Generic mode selection by compressed size is BACKGROUND infrastructure and is
not claimed as candidate IP. The router exists to provide a fair framework for
future proprietary KHEPRI-specific residual/motion mechanisms.
"""
import argparse, hashlib, json, shutil, struct, subprocess, tempfile, time
from pathlib import Path

from kstream_video_baseline import encode_file as temp_encode, decode_file as temp_decode
from kstream_video_motion_control import encode_file as mc_encode, decode_file as mc_decode

MAGIC=b"K5GR"
VERSION=2
HDR=struct.Struct("<4sBHHIIII")  # magic,ver,w,h,fpsn,fpsd,gop,route_span
ENT=struct.Struct("<BII")        # mode, raw_frames, compressed_bytes
MODE_TEMP=0
MODE_MC8R4=1

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

def frame_size(w,h):
    return w*h + 2*((w+1)//2)*((h+1)//2)

def encode_candidate(raw_chunk,mode,tmp,exe,w,h,fpsn,fpsd,gop,idx):
    src=tmp/f"g{idx}_{mode}.yuv"
    front=tmp/f"g{idx}_{mode}.front"
    arc=tmp/f"g{idx}_{mode}.aur"
    src.write_bytes(raw_chunk)
    t=time.perf_counter()
    if mode==MODE_TEMP:
        temp_encode(src,front,w,h,fpsn,fpsd,gop,3)
    else:
        mc_encode(src,front,w,h,fpsn,fpsd,gop,8,4)
    fe=time.perf_counter()-t
    ke=kcp(exe,front,arc)
    return arc.read_bytes(),fe+ke

def decode_candidate(payload,mode,tmp,exe,w,h,idx):
    arc=tmp/f"d{idx}.aur"; outdir=tmp/f"d{idx}_k"; front=tmp/f"d{idx}.front"; raw=tmp/f"d{idx}.yuv"
    arc.write_bytes(payload)
    kd=kdp(exe,arc,outdir)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1: raise RuntimeError("bad KHEPRI decode")
    shutil.copyfile(files[0],front)
    t=time.perf_counter()
    if mode==MODE_TEMP:
        temp_decode(front,raw)
    else:
        mc_decode(front,raw)
    fd=time.perf_counter()-t
    return raw.read_bytes(),kd+fd

def encode_file(src,dst,exe,w,h,fpsn,fpsd,gop,route_span):
    raw=src.read_bytes(); fs=frame_size(w,h)
    if len(raw)%fs: raise ValueError("incomplete frames")
    if route_span<gop or route_span%gop:
        raise ValueError("route_span must be a multiple of GOP")
    total=len(raw)//fs
    entries=[]; counts={MODE_TEMP:0,MODE_MC8R4:0}; enc_time=0.0
    with tempfile.TemporaryDirectory(prefix="ksv05_") as td:
        tmp=Path(td)
        for gi,off in enumerate(range(0,total,route_span)):
            n=min(route_span,total-off)
            chunk=raw[off*fs:(off+n)*fs]
            cand=[]
            for mode in (MODE_TEMP,MODE_MC8R4):
                payload,secs=encode_candidate(chunk,mode,tmp,exe,w,h,fpsn,fpsd,gop,gi)
                cand.append((len(payload),mode,payload,secs))
            _,mode,payload,secs=min(cand,key=lambda x:(x[0],x[1]))
            counts[mode]+=1
            enc_time+=secs
            entries.append((mode,n,payload))
        with dst.open("wb") as f:
            f.write(HDR.pack(MAGIC,VERSION,w,h,fpsn,fpsd,gop,route_span))
            for mode,n,payload in entries:
                f.write(ENT.pack(mode,n,len(payload)))
                f.write(payload)
    return counts,enc_time

def decode_file(src,dst,exe):
    b=src.read_bytes(); pos=0
    if len(b)<HDR.size: raise ValueError("truncated header")
    magic,ver,w,h,fpsn,fpsd,gop,route_span=HDR.unpack_from(b,pos); pos+=HDR.size
    if magic!=MAGIC or ver!=VERSION: raise ValueError("bad stream")
    out=bytearray(); dec_time=0.0; idx=0
    with tempfile.TemporaryDirectory(prefix="ksv05d_") as td:
        tmp=Path(td)
        while pos<len(b):
            if pos+ENT.size>len(b): raise ValueError("truncated entry")
            mode,n,cs=ENT.unpack_from(b,pos); pos+=ENT.size
            if mode not in (MODE_TEMP,MODE_MC8R4) or pos+cs>len(b):
                raise ValueError("bad entry")
            payload=b[pos:pos+cs]; pos+=cs
            raw,secs=decode_candidate(payload,mode,tmp,exe,w,h,idx)
            if len(raw)!=n*frame_size(w,h): raise ValueError("decoded size")
            out.extend(raw); dec_time+=secs; idx+=1
    dst.write_bytes(out)
    return dec_time

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    ap.add_argument("--clip",action="append",required=True)
    ap.add_argument("--route-span",type=int,default=10)
    a=ap.parse_args()
    out=Path(f"streaming/ksv05_out_{a.route_span}")
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for spec in a.clip:
        name,p,w,h,fpsn,fpsd,gop=spec.split(":")
        src=Path(p).resolve(); w=int(w); h=int(h); fpsn=int(fpsn); fpsd=int(fpsd); gop=int(gop)
        arc=out/f"{name}.k5gr"; dec=out/f"{name}.dec.yuv"
        counts,et=encode_file(src,arc,a.kephir,w,h,fpsn,fpsd,gop,a.route_span)
        dt=decode_file(arc,dec,a.kephir)
        ok=sha(src)==sha(dec)
        if not ok: raise SystemExit("SHA FAIL "+name)
        frames=src.stat().st_size//frame_size(w,h)
        duration=frames*fpsd/fpsn
        rows.append(dict(name=name,raw_bytes=src.stat().st_size,bytes=arc.stat().st_size,
                         ratio=arc.stat().st_size/src.stat().st_size,
                         frames=frames,route_span=a.route_span,
                         modes={"TEMP":counts[MODE_TEMP],"MC8R4":counts[MODE_MC8R4]},
                         encode_seconds=et,decode_seconds=dt,
                         encode_realtime_x=duration/et,decode_realtime_x=duration/dt,sha_ok=True))
        print(rows[-1],flush=True)
    result={"experiment":"KSV-05 adaptive GOP router","route_span":a.route_span,"rows":rows}
    (out/"ksv05_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
