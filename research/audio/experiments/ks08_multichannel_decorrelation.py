#!/usr/bin/env python3
import hashlib, math, struct, time
from pathlib import Path
from research.audio.lab import kstream_kmrl_frontend as kmrl

OUT=Path("results/audio/ks08_multichannel_decorrelation")
OUT.mkdir(parents=True,exist_ok=True)

def make_signal(channels, bits, frames=8192):
    hi=(1<<(bits-1))-1
    amp=max(1,hi//10)
    chans=[[] for _ in range(channels)]
    for i in range(frames):
        base=int(amp*math.sin(i*0.013))
        for c in range(channels):
            v=base
            if c%2: v += int(amp*0.20*math.sin(i*0.019 + c))
            else:   v += int(amp*0.15*math.sin(i*0.017 + c*0.3))
            if c==2: v=int(base*0.70)
            if c==3: v=int(amp*0.12*math.sin(i*0.005))
            v=max(-(1<<(bits-1)),min((1<<(bits-1))-1,v))
            chans[c].append(v)
    return chans

def interleave(chans):
    out=[]
    for i in range(len(chans[0])):
        for c in chans: out.append(c[i])
    return out

def pair_fwd(a,b):
    side=[x-y for x,y in zip(a,b)]
    mid=[y+(s>>1) for y,s in zip(b,side)]
    return mid,side

def pair_inv(mid,side):
    b=[m-(s>>1) for m,s in zip(mid,side)]
    a=[s+y for s,y in zip(side,b)]
    return a,b

def independent(ch):
    return [list(x) for x in ch], lambda comps:[list(x) for x in comps]

def pairwise(ch):
    comps=[]
    pairs=[]
    i=0
    while i<len(ch):
        if i+1<len(ch):
            m,s=pair_fwd(ch[i],ch[i+1]); comps.extend([m,s]); pairs.append((len(comps)-2,len(comps)-1))
            i+=2
        else:
            comps.append(list(ch[i])); i+=1
    def inv(cs):
        out=[];i=0
        while i<len(cs):
            if i+1<len(cs):
                a,b=pair_inv(cs[i],cs[i+1]);out.extend([a,b]);i+=2
            else: out.append(list(cs[i]));i+=1
        return out
    return comps,inv

def hierarchical(ch):
    # Pair L/R and surround pairs first, then correlate pair mids with center when present.
    cs=[list(x) for x in ch]
    if len(cs)>=2:
        cs[0],cs[1]=pair_fwd(cs[0],cs[1])
    if len(cs)>=6:
        cs[4],cs[5]=pair_fwd(cs[4],cs[5])
    if len(cs)>=8:
        cs[6],cs[7]=pair_fwd(cs[6],cs[7])
    if len(cs)>=3:
        cs[0],cs[2]=pair_fwd(cs[0],cs[2])
    def inv(x):
        y=[list(v) for v in x]
        if len(y)>=3:
            y[0],y[2]=pair_inv(y[0],y[2])
        if len(y)>=8:
            y[6],y[7]=pair_inv(y[6],y[7])
        if len(y)>=6:
            y[4],y[5]=pair_inv(y[4],y[5])
        if len(y)>=2:
            y[0],y[1]=pair_inv(y[0],y[1])
        return y
    return cs,inv

def encode_components(comps):
    payload=bytearray()
    for comp in comps:
        payload.extend(kmrl.encode_component(comp))
    return bytes(payload)

def run_case(name,channels,bits):
    src=make_signal(channels,bits)
    raw=kmrl.pack_pcm_le(interleave(src),bits)
    for mode,fn in [("independent",independent),("pairwise",pairwise),("hierarchical",hierarchical)]:
        t0=time.perf_counter()
        comps,inv=fn(src)
        payload=encode_components(comps)
        t1=time.perf_counter()
        restored=inv(comps)
        dec=kmrl.pack_pcm_le(interleave(restored),bits)
        if dec!=raw:
            raise SystemExit(f"ROUNDTRIP_FAIL {name} {mode}")
        print(f"KS08_PASS case={name} mode={mode} channels={channels} bits={bits} raw_bytes={len(raw)} payload_bytes={len(payload)} transform_encode_ms={(t1-t0)*1000:.6f} sha_ok=1")

def main():
    run_case("surround51_24",6,24)
    run_case("surround71_24",8,24)
    run_case("surround51_32",6,32)
    run_case("surround71_32",8,32)

if __name__=="__main__":
    main()
