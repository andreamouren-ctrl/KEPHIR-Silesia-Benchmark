#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from kstream_kmrl_frontend import encode_file as encode_kmrl0, decode_file as decode_kmrl0
from kstream_kmrl_lab import encode_file as encode_lab, decode_file as decode_lab

OUT=Path("streaming/ks04_out")
RATE=48000
CHANNELS=2
BITS=16
BLOCK_MS=20
BLOCK_SAMPLES=RATE*BLOCK_MS//1000


def sha(p:Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def timed(cmd):
    t0=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t0


def kephir(exe:Path,src:Path,tag:str):
    arc=OUT/f"{tag}.aur"; dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/src.name
    if sha(restored)!=sha(src): raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size,es,ds


def run_front(exe,raw,tag,kind):
    front=OUT/f"{tag}.front"; restored=OUT/f"{tag}.restored.raw"
    t0=time.perf_counter()
    if kind=="kmrl0":
        encode_kmrl0(raw,front,CHANNELS,RATE,BLOCK_MS)
    else:
        encode_lab(raw,front,CHANNELS,RATE,BLOCK_MS,int(kind))
    fe=time.perf_counter()-t0

    t0=time.perf_counter()
    if kind=="kmrl0": decode_kmrl0(front,restored)
    else: decode_lab(front,restored)
    fd=time.perf_counter()-t0
    if sha(restored)!=sha(raw): raise SystemExit(f"FRONTEND SHA FAIL {tag}")

    kb,ke,kd=kephir(exe,front,tag)
    return dict(codec=tag,frontend_bytes=front.stat().st_size,bytes=kb,
                encode_seconds=fe+ke,decode_seconds=fd+kd,
                frontend_encode_seconds=fe,frontend_decode_seconds=fd,
                backend_encode_seconds=ke,backend_decode_seconds=kd,sha_ok=True)


def run_flac(raw):
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
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir33"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve(); exe=a.kephir
    raw_bytes=raw.stat().st_size
    if raw_bytes%(CHANNELS*2): raise SystemExit("bad PCM")
    duration=raw_bytes/(RATE*CHANNELS*2)

    rows=[
        run_front(exe,raw,"KMRL0_RESET_PACKED","kmrl0"),
        run_front(exe,raw,"KMRL1_CARRY_PACKED","1"),
        run_front(exe,raw,"KMRL1_FULL256","2"),
        run_front(exe,raw,"KMRL1_CLASS_FULL256","3"),
        run_flac(raw),
    ]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/raw_bytes
        r["bits_per_sample"]=8*r["bytes"]/(raw_bytes/2)
        r["encode_realtime_x"]=duration/r["encode_seconds"]
        r["decode_realtime_x"]=duration/r["decode_seconds"]

    base=rows[0]["bytes"]
    for r in rows:
        r["delta_vs_kmrl0_percent"]=100*(r["bytes"]-base)/base

    result=dict(
        experiment="KS-04 KMRL geometry real-audio sweep",
        source=dict(bytes=raw_bytes,duration_seconds=duration,sha256=sha(raw),
                    profile="Sintel-derived stereo s16le 48kHz"),
        block_ms=BLOCK_MS,
        rows=rows,
        rule="Only three KMRL geometry variants are tested at this checkpoint; all results must be bit-exact."
    )
    (OUT/"ks04_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
