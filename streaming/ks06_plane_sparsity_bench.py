#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
import kstream_kmrl_lab as lab

OUT=Path("streaming/ks06_out")
RATE=48000
CHANNELS=2
BLOCK_MS=20
LAYOUT=2
TILE=256

def sha(p:Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def enc_tail16(us, with_class=False):
    if with_class:
        raise ValueError("TAIL16 is layout-2 only")
    pc=lab.plane_count(us)
    out=bytearray([pc])
    n=len(us)
    for sh in range(0,8*pc,8):
        plane=bytearray((u>>sh)&255 for u in us)
        if n<TILE:
            plane.extend(b"\0"*(TILE-n))
        last=-1
        for i in range(TILE-1,-1,-1):
            if plane[i]:
                last=i
                break
        units=0 if last<0 else ((last+16)//16)
        if units>16:
            units=16
        out.append(units)
        out.extend(plane[:units*16])
    return bytes(out)

def dec_tail16(buf,pos,n,with_class=False):
    if with_class:
        raise ValueError("TAIL16 is layout-2 only")
    if pos>=len(buf): raise ValueError("truncated plane count")
    pc=buf[pos]; pos+=1
    if pc<1 or pc>4: raise ValueError("bad plane count")
    planes=[]
    for _ in range(pc):
        if pos>=len(buf): raise ValueError("truncated tail16 length")
        units=buf[pos]; pos+=1
        if units>16: raise ValueError("bad tail16 units")
        take=units*16
        if pos+take>len(buf): raise ValueError("truncated tail16 plane")
        plane=bytearray(TILE)
        plane[:take]=buf[pos:pos+take]
        pos+=take
        planes.append(plane)
    us=[]
    for i in range(n):
        u=0
        for p in range(pc):
            u|=planes[p][i]<<(8*p)
        us.append(u)
    return us,pos

def enc_mask16(us, with_class=False):
    if with_class:
        raise ValueError("MASK16 is layout-2 only")
    pc=lab.plane_count(us)
    out=bytearray([pc])
    n=len(us)
    for sh in range(0,8*pc,8):
        plane=bytearray((u>>sh)&255 for u in us)
        if n<TILE:
            plane.extend(b"\0"*(TILE-n))
        mask=0
        groups=[]
        for g in range(16):
            chunk=bytes(plane[g*16:(g+1)*16])
            if any(chunk):
                mask|=(1<<g)
                groups.append(chunk)
        out.extend(mask.to_bytes(2,"little"))
        for chunk in groups:
            out.extend(chunk)
    return bytes(out)

def dec_mask16(buf,pos,n,with_class=False):
    if with_class:
        raise ValueError("MASK16 is layout-2 only")
    if pos>=len(buf): raise ValueError("truncated plane count")
    pc=buf[pos]; pos+=1
    if pc<1 or pc>4: raise ValueError("bad plane count")
    planes=[]
    for _ in range(pc):
        if pos+2>len(buf): raise ValueError("truncated mask")
        mask=int.from_bytes(buf[pos:pos+2],"little"); pos+=2
        plane=bytearray(TILE)
        for g in range(16):
            if mask&(1<<g):
                if pos+16>len(buf): raise ValueError("truncated masked group")
                plane[g*16:(g+1)*16]=buf[pos:pos+16]
                pos+=16
        planes.append(plane)
    us=[]
    for i in range(n):
        u=0
        for p in range(pc):
            u|=planes[p][i]<<(8*p)
        us.append(u)
    return us,pos

def kephir(exe,src,tag):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/src.name
    if sha(restored)!=sha(src): raise SystemExit("KEPHIR SHA FAIL "+tag)
    return arc.stat().st_size,es,ds

def run_variant(exe,raw,tag,mode):
    orig_enc,orig_dec=lab.enc_fullplanes,lab.dec_fullplanes
    if mode=="BASE":
        enc,dec=orig_enc,orig_dec
    elif mode=="TAIL16":
        enc,dec=enc_tail16,dec_tail16
    elif mode=="MASK16":
        enc,dec=enc_mask16,dec_mask16
    else:
        raise ValueError(mode)
    lab.enc_fullplanes,lab.dec_fullplanes=enc,dec
    try:
        front=OUT/f"{tag}.front"; restored=OUT/f"{tag}.raw"
        t=time.perf_counter(); lab.encode_file(raw,front,CHANNELS,RATE,BLOCK_MS,LAYOUT); fe=time.perf_counter()-t
        t=time.perf_counter(); lab.decode_file(front,restored); fd=time.perf_counter()-t
        if sha(restored)!=sha(raw): raise SystemExit("FRONTEND SHA FAIL "+tag)
        kb,ke,kd=kephir(exe,front,tag)
        return {"codec":tag,"geometry":mode,"frontend_bytes":front.stat().st_size,"bytes":kb,
                "frontend_encode_seconds":fe,"frontend_decode_seconds":fd,
                "backend_encode_seconds":ke,"backend_decode_seconds":kd,"sha_ok":True}
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=orig_enc,orig_dec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir33"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); rb=raw.stat().st_size
    duration=rb/(RATE*CHANNELS*2)
    variants=[("FULL256_BASE","BASE"),("FULL256_TAIL16","TAIL16"),("FULL256_MASK16","MASK16")]
    rows=[run_variant(a.kephir,raw,*v) for v in variants]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/rb
        r["delta_vs_base_bytes"]=r["bytes"]-base
        r["delta_vs_base_percent"]=100*(r["bytes"]-base)/base
        r["encode_realtime_x"]=duration/(r["frontend_encode_seconds"]+r["backend_encode_seconds"])
        r["decode_realtime_x"]=duration/(r["frontend_decode_seconds"]+r["backend_decode_seconds"])
    result={"experiment":"KS-06 topology-preserving FULL256 sparsity",
            "source":{"bytes":rb,"duration_seconds":duration,"sha256":sha(raw),
                      "profile":"Sintel-derived stereo s16le 48kHz"},
            "block_ms":BLOCK_MS,"rows":rows,
            "promotion_rule":"Promote only if final EXP-33H bytes improve and SHA remains exact."}
    (OUT/"ks06_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
