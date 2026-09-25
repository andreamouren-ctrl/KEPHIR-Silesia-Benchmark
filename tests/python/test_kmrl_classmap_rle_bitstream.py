#!/usr/bin/env python3
import math, random, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
KMRL=ROOT/"research/audio/lab/kstream_kmrl_frontend.py"
OUT=ROOT/"results/audio/classmap_rle_bitstream"
OUT.mkdir(parents=True,exist_ok=True)

CASES=[]
for bits in (16,24,32):
    for kind in ("tone","speechlike","transient","noisy"):
        CASES.append((f"{kind}_{bits}",kind,bits))

def pack(v,bits):
    if bits==16:
        return int(v).to_bytes(2,"little",signed=True)
    if bits==24:
        u=v & 0xFFFFFF
        return bytes((u&255,(u>>8)&255,(u>>16)&255))
    return int(v).to_bytes(4,"little",signed=True)

def make_pcm(kind,bits,n=32768):
    hi=(1<<(bits-1))-1
    lo=-(1<<(bits-1))
    amp=max(1,hi//12)
    rng=random.Random(20260925)
    out=bytearray()
    for i in range(n):
        if kind=="tone":
            v=int(amp*math.sin(i*0.013)+amp*0.20*math.sin(i*0.031))
        elif kind=="speechlike":
            env=0.35+0.65*(0.5+0.5*math.sin(i*0.0009))
            v=int(env*(amp*math.sin(i*0.021)+amp*0.30*math.sin(i*0.047)))
        elif kind=="transient":
            v=int(amp*0.45*math.sin(i*0.017))
            if i%997<8:v+=int(amp*2.2*(1-(i%997)/8))
        else:
            v=int(amp*0.55*math.sin(i*0.019)+rng.randint(-amp//5,amp//5))
        out.extend(pack(max(lo,min(hi,v)),bits))
    return bytes(out)

def main():
    for name,kind,bits in CASES:
        src=OUT/(name+".pcm")
        enc=OUT/(name+".kmrl")
        dec=OUT/(name+".dec.pcm")
        raw=make_pcm(kind,bits)
        src.write_bytes(raw)
        subprocess.run([sys.executable,str(KMRL),"encode",str(src),str(enc),
                        "--channels","1","--rate","48000","--bits",str(bits),
                        "--block-ms","20"],check=True)
        subprocess.run([sys.executable,str(KMRL),"decode",str(enc),str(dec)],check=True)
        got=dec.read_bytes()
        if got!=raw:
            raise SystemExit(f"ROUNDTRIP_FAIL {name}")
        print(f"CLASSMAP_RLE_BITSTREAM_PASS case={name} bits={bits} raw_bytes={len(raw)} encoded_bytes={enc.stat().st_size} sha_ok=1")
    print(f"CLASSMAP_RLE_BITSTREAM_ALL_PASS cases={len(CASES)}")

if __name__=="__main__":
    main()
