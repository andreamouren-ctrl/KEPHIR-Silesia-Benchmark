#!/usr/bin/env python3
import hashlib, json, shutil, subprocess, time
from pathlib import Path

from kstream_kmrl_lab import encode_file as encode_kmrl1, decode_file as decode_kmrl1
from kstream_ktarp_frontend import encode_file as encode_ktarp, decode_file as decode_ktarp

OUT=Path("streaming/ks05_out")
RATE=48000; CHANNELS=2; BITS=16; BLOCK_MS=20; BLOCK_SAMPLES=960

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def kephir(exe,src,tag):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(Path(exe).resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(Path(exe).resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/Path(src).name
    if sha(restored)!=sha(src): raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size,es,ds

def front_roundtrip(exe,raw,tag,kind):
    front=OUT/f"{tag}.front"; restored=OUT/f"{tag}.raw"
    t=time.perf_counter()
    if kind=="baseline":
        encode_kmrl1(raw,front,CHANNELS,RATE,BLOCK_MS,2)
    else:
        encode_ktarp(raw,front,CHANNELS,RATE,BLOCK_MS,int(kind))
    fe=time.perf_counter()-t

    t=time.perf_counter()
    if kind=="baseline": decode_kmrl1(front,restored)
    else: decode_ktarp(front,restored)
    fd=time.perf_counter()-t
    if sha(restored)!=sha(raw): raise SystemExit(f"FRONT SHA FAIL {tag}")

    kb,ke,kd=kephir(exe,front,tag)
    return dict(codec=tag,frontend_bytes=front.stat().st_size,bytes=kb,
                encode_seconds=fe+ke,decode_seconds=fd+kd,
                frontend_encode_seconds=fe,frontend_decode_seconds=fd,
                backend_encode_seconds=ke,backend_decode_seconds=kd,sha_ok=True)

def flac(raw):
    out=OUT/"flac20.flac"; restored=OUT/"flac20.raw"
    if out.exists(): out.unlink()
    if restored.exists(): restored.unlink()
    es=timed(["flac","-5","-f","-s",f"--blocksize={BLOCK_SAMPLES}",
              "--no-padding","--no-seektable","--force-raw-format",
              "--endian=little","--sign=signed",f"--channels={CHANNELS}",
              f"--bps={BITS}",f"--sample-rate={RATE}","-o",str(out),str(raw)])
    ds=timed(["flac","-d","-f","-s","--force-raw-format",
              "--endian=little","--sign=signed","-o",str(restored),str(out)])
    if sha(restored)!=sha(raw): raise SystemExit("FLAC SHA FAIL")
    return dict(codec="FLAC5_BLOCK960",bytes=out.stat().st_size,
                encode_seconds=es,decode_seconds=ds,sha_ok=True)

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--raw",type=Path,required=True); ap.add_argument("--kephir",default="./kephir33")
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); raw_bytes=raw.stat().st_size
    duration=raw_bytes/(RATE*CHANNELS*2)

    rows=[
        front_roundtrip(a.kephir,raw,"KMRL1_FULL256","baseline"),
        front_roundtrip(a.kephir,raw,"KTARP_FIXED_TRANSPOSE","0"),
        front_roundtrip(a.kephir,raw,"KTARP_EQUAL_AFFINITY","1"),
        front_roundtrip(a.kephir,raw,"KTARP_RUN_AFFINITY","2"),
        flac(raw),
    ]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/raw_bytes
        r["bits_per_sample"]=8*r["bytes"]/(raw_bytes/2)
        r["delta_vs_full256_percent"]=100*(r["bytes"]-base)/base
        r["encode_realtime_x"]=duration/r["encode_seconds"]
        r["decode_realtime_x"]=duration/r["decode_seconds"]

    result=dict(
      experiment="KS-05 KTARP topology-adaptive permutation",
      source=dict(bytes=raw_bytes,duration_seconds=duration,sha256=sha(raw),profile="Sintel-derived stereo s16le 48kHz"),
      block_ms=BLOCK_MS,
      rows=rows,
      rule="Adaptive topology is promoted only if it beats both fixed row-major FULL256 and fixed-transpose control while remaining bit-exact."
    )
    (OUT/"ks05_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
