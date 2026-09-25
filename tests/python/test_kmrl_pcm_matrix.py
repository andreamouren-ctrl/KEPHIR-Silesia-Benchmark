#!/usr/bin/env python3
import hashlib
import math
import struct
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
KMRL=ROOT/"research/audio/lab/kstream_kmrl_frontend.py"
OUT=ROOT/"results/audio/pcm_matrix"

CASES=[
    ("mono16",1,16,44100),
    ("mono24",1,24,48000),
    ("mono32",1,32,96000),
    ("stereo16",2,16,48000),
    ("stereo24",2,24,96000),
    ("stereo32",2,32,192000),
    ("surround51_16",6,16,48000),
    ("surround51_24",6,24,96000),
    ("surround51_32",6,32,192000),
]

def pack_sample(v,bits):
    if bits==16:
        return struct.pack("<h",v)
    if bits==24:
        u=v & 0xFFFFFF
        return bytes((u&255,(u>>8)&255,(u>>16)&255))
    if bits==32:
        return struct.pack("<i",v)
    raise ValueError(bits)

def make_pcm(ch,bits,rate,frames=4096):
    lo=-(1<<(bits-1)); hi=(1<<(bits-1))-1
    amp=max(1,hi//8)
    out=bytearray()
    for i in range(frames):
        for c in range(ch):
            # Deterministic correlated multichannel signal with transients.
            v=int(amp*math.sin((i*(c+1)+17*c)*0.017))
            if i%257==0: v=max(lo,min(hi,v + (amp//2 if c%2==0 else -amp//3)))
            out.extend(pack_sample(v,bits))
    return bytes(out)

def sha(b): return hashlib.sha256(b).hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for name,ch,bits,rate in CASES:
        raw=make_pcm(ch,bits,rate)
        src=OUT/(name+".pcm")
        enc=OUT/(name+".kmrl")
        dec=OUT/(name+".decoded.pcm")
        src.write_bytes(raw)
        subprocess.run([sys.executable,str(KMRL),"encode",str(src),str(enc),
                        "--channels",str(ch),"--rate",str(rate),"--bits",str(bits),
                        "--block-ms","20"],check=True)
        subprocess.run([sys.executable,str(KMRL),"decode",str(enc),str(dec)],check=True)
        got=dec.read_bytes()
        if got!=raw:
            raise SystemExit(f"ROUNDTRIP_FAIL {name} src={sha(raw)} dec={sha(got)}")
        print(f"AUDIO_PCM_MATRIX_PASS case={name} channels={ch} bits={bits} rate={rate} raw_bytes={len(raw)} encoded_bytes={enc.stat().st_size} sha_ok=1")
    print(f"AUDIO_PCM_MATRIX_ALL_PASS cases={len(CASES)}")

if __name__=="__main__":
    main()
