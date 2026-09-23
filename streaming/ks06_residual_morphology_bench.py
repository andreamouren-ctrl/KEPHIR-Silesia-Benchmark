#!/usr/bin/env python3
import hashlib, json, shutil, subprocess, time
from pathlib import Path

from kstream_kmrl_lab import encode_file as encode_full, decode_file as decode_full
from kstream_residual_morphology import encode_file as encode_morph, decode_file as decode_morph

OUT=Path("streaming/ks06_out")
RATE=48000; CH=2; BITS=16; BLOCK_MS=20; FLAC_BLOCK=960

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

def variant(exe,raw,tag,layout):
    front=OUT/f"{tag}.front"; restored=OUT/f"{tag}.raw"
    t=time.perf_counter()
    if layout==0: encode_full(raw,front,CH,RATE,BLOCK_MS,2)
    else: encode_morph(raw,front,CH,RATE,BLOCK_MS,layout)
    fe=time.perf_counter()-t
    t=time.perf_counter()
    if layout==0: decode_full(front,restored)
    else: decode_morph(front,restored)
    fd=time.perf_counter()-t
    if sha(restored)!=sha(raw): raise SystemExit(f"FRONT SHA FAIL {tag}")
    kb,ke,kd=kephir(exe,front,tag)
    return dict(codec=tag,frontend_bytes=front.stat().st_size,bytes=kb,
                encode_seconds=fe+ke,decode_seconds=fd+kd,
                frontend_encode_seconds=fe,frontend_decode_seconds=fd,
                backend_encode_seconds=ke,backend_decode_seconds=kd,sha_ok=True)

def flac(raw):
    out=OUT/"ref.flac"; dec=OUT/"ref.raw"
    if out.exists(): out.unlink()
    if dec.exists(): dec.unlink()
    ce=timed(["flac","-5","-f","-s",f"--blocksize={FLAC_BLOCK}","--no-padding","--no-seektable",
              "--force-raw-format","--endian=little","--sign=signed",f"--channels={CH}",
              f"--bps={BITS}",f"--sample-rate={RATE}","-o",str(out),str(raw)])
    cd=timed(["flac","-d","-f","-s","--force-raw-format","--endian=little","--sign=signed","-o",str(dec),str(out)])
    if sha(dec)!=sha(raw): raise SystemExit("FLAC SHA FAIL")
    return dict(codec="FLAC5_BLOCK960",bytes=out.stat().st_size,encode_seconds=ce,decode_seconds=cd,sha_ok=True)

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--raw",type=Path,required=True); ap.add_argument("--kephir",default="./kephir33")
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); raw_bytes=raw.stat().st_size; duration=raw_bytes/(RATE*CH*2)
    rows=[
      variant(a.kephir,raw,"KMRL1_FULL256_ZIGZAG",0),
      variant(a.kephir,raw,"RSM_PACKED_SIGN",1),
      variant(a.kephir,raw,"RSM_FULL256_SIGN",2),
      variant(a.kephir,raw,"RSM_TRANSITION_SIGN",3),
      flac(raw),
    ]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/raw_bytes
        r["bits_per_sample"]=8*r["bytes"]/(raw_bytes/2)
        r["delta_vs_full256_percent"]=100*(r["bytes"]-base)/base
        r["encode_realtime_x"]=duration/r["encode_seconds"]
        r["decode_realtime_x"]=duration/r["decode_seconds"]
    result=dict(experiment="KS-06 residual sign/magnitude morphology",
                source=dict(bytes=raw_bytes,duration_seconds=duration,sha256=sha(raw),
                            profile="Sintel-derived stereo s16le 48kHz"),
                block_ms=BLOCK_MS,rows=rows,
                rule="These are background/control transforms. A win improves the technical baseline but is not itself a patentability claim.")
    (OUT/"ks06_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
