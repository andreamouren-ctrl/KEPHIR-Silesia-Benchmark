#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path

import kstream_kmrl_lab as lab
from ks06_plane_sparsity_bench import enc_tail16, dec_tail16

OUT=Path("streaming/ks07b_out")
RATE=48000; CHANNELS=2; BLOCK_MS=20; LAYOUT=2

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def timed(cmd):
    t=time.perf_counter(); subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); return time.perf_counter()-t

def make_front(raw):
    front=OUT/"tail16.front"; restored=OUT/"tail16.raw"
    oe,od=lab.enc_fullplanes,lab.dec_fullplanes
    lab.enc_fullplanes,lab.dec_fullplanes=enc_tail16,dec_tail16
    try:
        lab.encode_file(raw,front,CHANNELS,RATE,BLOCK_MS,LAYOUT)
        lab.decode_file(front,restored)
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=oe,od
    if sha(restored)!=sha(raw): raise SystemExit("frontend SHA fail")
    return front

def roundtrip(exe,front,tag):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"{tag}_dec"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"])
    if sha(dec/front.name)!=sha(front): raise SystemExit(tag+" SHA fail")
    return {"backend":tag,"bytes":arc.stat().st_size,"encode_seconds":es,"decode_seconds":ds,"sha_ok":True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--exp33",type=Path,default=Path("./kephir33"))
    ap.add_argument("--exp37",type=Path,default=Path("./kephir37"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); rb=raw.stat().st_size
    front=make_front(raw)
    rows=[roundtrip(a.exp33,front,"EXP33H"),roundtrip(a.exp37,front,"EXP37A")]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/rb
        r["delta_vs_exp33_bytes"]=r["bytes"]-base
        r["delta_vs_exp33_percent"]=100*(r["bytes"]-base)/base
    result={"experiment":"KS-07B direct core migration","source_bytes":rb,"frontend_bytes":front.stat().st_size,
            "rows":rows,"promotion_rule":"Promote EXP37A if it beats EXP33H and roundtrip is bit-exact."}
    (OUT/"ks07b_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
