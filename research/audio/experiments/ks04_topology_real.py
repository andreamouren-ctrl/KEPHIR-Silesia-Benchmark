#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path

import kstream_kmrl_frontend as kmrl
from ks03_topology_bench import make_encoder

OUT=Path("streaming/ks04_out")
RATE=48000; CHANNELS=2; BLOCK_MS=20

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def timed(cmd, **kw):
    t=time.perf_counter(); subprocess.run(cmd,check=True,**kw); return time.perf_counter()-t

def kephir(exe, src, tag):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    e=timed([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    d=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if sha(dec/src.name)!=sha(src): raise SystemExit("KEPHIR SHA FAIL "+tag)
    return arc.stat().st_size,e,d

def front_variant(exe, raw, tag, a16, a256):
    old=kmrl.encode_component
    kmrl.encode_component=make_encoder(a16,a256)
    try:
        front=OUT/f"{tag}.kmr"; restored=OUT/f"{tag}.raw"
        t=time.perf_counter(); kmrl.encode_file(raw,front,channels=2,rate=RATE,block_ms=BLOCK_MS); fe=time.perf_counter()-t
        t=time.perf_counter(); kmrl.decode_file(front,restored); fd=time.perf_counter()-t
        if sha(restored)!=sha(raw): raise SystemExit("FRONTEND SHA FAIL "+tag)
        kb,ke,kd=kephir(exe,front,tag)
        return dict(codec=tag,alpha16=a16,alpha256=a256,frontend_bytes=front.stat().st_size,bytes=kb,
                    frontend_encode_s=fe,frontend_decode_s=fd,backend_encode_s=ke,backend_decode_s=kd,sha_ok=True)
    finally:
        kmrl.encode_component=old

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir33"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); exe=a.kephir
    rb=raw.stat().st_size
    vars=[("KMRL_BASE",0.0,0.0),("KMRL_TOPO_LIGHT",0.06,0.12),("KMRL_TOPO_STRONG",0.14,0.28)]
    rows=[front_variant(exe,raw,*v) for v in vars]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/rb
        r["delta_vs_base_bytes"]=r["bytes"]-base
        r["delta_vs_base_percent"]=100*(r["bytes"]-base)/base
    result={"experiment":"KS-04 real-audio topology-aware predictor selection",
            "source_bytes":rb,"source_sha256":sha(raw),"rows":rows,
            "promotion_rule":"Promote only if final KEPHIR bytes improve and SHA remains exact."}
    (OUT/"ks04_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
