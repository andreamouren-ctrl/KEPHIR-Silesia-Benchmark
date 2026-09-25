#!/usr/bin/env python3
import hashlib, math, struct, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
KMRL=ROOT/"research/audio/lab/kstream_kmrl_frontend.py"
OUT=ROOT/"results/audio/adaptive_multichannel"
OUT.mkdir(parents=True,exist_ok=True)

CASES=[
    ("surround51_24",6,24,96000),
    ("surround71_24",8,24,96000),
    ("surround51_32",6,32,192000),
    ("surround71_32",8,32,192000),
]

def pack(v,bits):
    if bits==24:
        u=v & 0xFFFFFF
        return bytes((u&255,(u>>8)&255,(u>>16)&255))
    return struct.pack("<i",v)

def make_pcm(ch,bits,frames=8192):
    hi=(1<<(bits-1))-1
    lo=-(1<<(bits-1))
    amp=max(1,hi//10)
    out=bytearray()
    for i in range(frames):
        base=int(amp*math.sin(i*0.013))
        vals=[]
        for c in range(ch):
            v=base
            if c%2: v += int(amp*0.20*math.sin(i*0.019 + c))
            else: v += int(amp*0.15*math.sin(i*0.017 + c*0.3))
            if c==2: v=int(base*0.70)
            if c==3: v=int(amp*0.12*math.sin(i*0.005))
            vals.append(max(lo,min(hi,v)))
        for v in vals: out.extend(pack(v,bits))
    return bytes(out)

def sha(b): return hashlib.sha256(b).hexdigest()

def run_mode(name,ch,bits,rate,mode):
    src=OUT/(name+".pcm")
    enc=OUT/(name+"."+mode+".kmrl")
    dec=OUT/(name+"."+mode+".dec.pcm")
    t0=time.perf_counter()
    subprocess.run([sys.executable,str(KMRL),"encode",str(src),str(enc),
                    "--channels",str(ch),"--rate",str(rate),"--bits",str(bits),
                    "--block-ms","20","--multichannel-mode",mode],check=True)
    t1=time.perf_counter()
    subprocess.run([sys.executable,str(KMRL),"decode",str(enc),str(dec)],check=True)
    t2=time.perf_counter()
    raw=src.read_bytes(); got=dec.read_bytes()
    if raw!=got:
        raise SystemExit(f"ROUNDTRIP_FAIL {name} {mode} src={sha(raw)} dec={sha(got)}")
    return enc.stat().st_size,(t1-t0)*1000,(t2-t1)*1000

def main():
    for name,ch,bits,rate in CASES:
        src=OUT/(name+".pcm")
        src.write_bytes(make_pcm(ch,bits))
        rows={}
        for mode in ("independent","hierarchical","adaptive"):
            rows[mode]=run_mode(name,ch,bits,rate,mode)
            sz,enc_ms,dec_ms=rows[mode]
            print(f"ADAPTIVE_MC_PASS case={name} mode={mode} channels={ch} bits={bits} encoded_bytes={sz} encode_ms={enc_ms:.6f} decode_ms={dec_ms:.6f} sha_ok=1")
        ind=rows["independent"][0]
        ada=rows["adaptive"][0]
        if bits==24 and ada>ind:
            raise SystemExit(f"ADAPTIVE_24_REGRESSION {name} independent={ind} adaptive={ada}")
        if bits==32 and ada>int(ind*0.985):
            raise SystemExit(f"ADAPTIVE_32_GAIN_TOO_SMALL {name} independent={ind} adaptive={ada}")
    print("ADAPTIVE_MC_ALL_PASS cases=4")

if __name__=="__main__":
    main()
