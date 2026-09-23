#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path

import kstream_kmrl_lab as lab
from ks06_plane_sparsity_bench import enc_tail16, dec_tail16
from kstream_exp44_backend import encode_file as exp44_encode, decode_file as exp44_decode

OUT=Path("streaming/ks07_out")
RATE=48000
CHANNELS=2
BLOCK_MS=20
LAYOUT=2

def sha(p:Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def build_tail16(raw:Path):
    front=OUT/"tail16.front"
    restored=OUT/"tail16.restored.raw"
    olde,oldd=lab.enc_fullplanes,lab.dec_fullplanes
    lab.enc_fullplanes,lab.dec_fullplanes=enc_tail16,dec_tail16
    try:
        t=time.perf_counter()
        lab.encode_file(raw,front,CHANNELS,RATE,BLOCK_MS,LAYOUT)
        fe=time.perf_counter()-t
        t=time.perf_counter()
        lab.decode_file(front,restored)
        fd=time.perf_counter()-t
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=olde,oldd
    if sha(restored)!=sha(raw): raise SystemExit("TAIL16 SHA FAIL")
    return front,fe,fd

def exp33_roundtrip(exe,front):
    arc=OUT/"tail16_exp33.aur"; dec=OUT/"tail16_exp33_dec"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/front.name
    if sha(restored)!=sha(front): raise SystemExit("EXP33 SHA FAIL")
    return arc.stat().st_size,es,ds

def exp44_roundtrip(exe,front):
    arc=OUT/"tail16_exp44.k44s"; restored=OUT/"tail16_exp44.front"
    t=time.perf_counter(); modes=exp44_encode(front,arc,exe); es=time.perf_counter()-t
    t=time.perf_counter(); exp44_decode(arc,restored,exe); ds=time.perf_counter()-t
    if sha(restored)!=sha(front): raise SystemExit("EXP44 SHA FAIL")
    return arc.stat().st_size,es,ds,modes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--exp33",type=Path,default=Path("./kephir33"))
    ap.add_argument("--exp37",type=Path,default=Path("./kephir37"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); rb=raw.stat().st_size
    duration=rb/(RATE*CHANNELS*2)

    front,fe,fd=build_tail16(raw)
    s33,e33,d33=exp33_roundtrip(a.exp33,front)
    s44,e44,d44,modes=exp44_roundtrip(a.exp37,front)

    rows=[
      {"backend":"EXP33H","bytes":s33,"backend_encode_seconds":e33,"backend_decode_seconds":d33},
      {"backend":"EXP44_STRUCTURAL_ROUTER","bytes":s44,"backend_encode_seconds":e44,"backend_decode_seconds":d44,"modes":modes},
    ]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/rb
        r["total_encode_realtime_x"]=duration/(fe+r["backend_encode_seconds"])
        r["total_decode_realtime_x"]=duration/(fd+r["backend_decode_seconds"])

    result={
      "experiment":"KS-07 migrate streaming codec backend from EXP-33H to EXP-44",
      "source":{"bytes":rb,"duration_seconds":duration,"sha256":sha(raw),"profile":"Sintel-derived stereo s16le 48kHz"},
      "frontend":{"name":"KMRL FULL256 TAIL16","bytes":front.stat().st_size,"encode_seconds":fe,"decode_seconds":fd},
      "rows":rows,
      "exp44_delta_vs_exp33_bytes":s44-s33,
      "exp44_delta_vs_exp33_percent":100*(s44-s33)/s33,
      "promotion_rule":"Promote EXP-44 backend if final bytes improve and the complete roundtrip remains bit-exact."
    }
    (OUT/"ks07_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
