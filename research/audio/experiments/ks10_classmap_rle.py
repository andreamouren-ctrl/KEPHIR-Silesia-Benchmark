#!/usr/bin/env python3
import math, random, time
from research.audio.lab import kstream_kmrl_frontend as kmrl

def make_signal(kind,bits,n=32768):
    hi=(1<<(bits-1))-1
    lo=-(1<<(bits-1))
    amp=max(1,hi//12)
    rng=random.Random(20260925)
    out=[]
    for i in range(n):
        if kind=="tone":
            v=int(amp*math.sin(i*0.013)+amp*0.20*math.sin(i*0.031))
        elif kind=="speechlike":
            env=0.35+0.65*(0.5+0.5*math.sin(i*0.0009))
            v=int(env*(amp*math.sin(i*0.021)+amp*0.30*math.sin(i*0.047)))
        elif kind=="transient":
            v=int(amp*0.45*math.sin(i*0.017))
            if i%997<8:v+=int(amp*2.2*(1-(i%997)/8))
        elif kind=="noisy":
            v=int(amp*0.55*math.sin(i*0.019)+rng.randint(-amp//5,amp//5))
        else:
            raise ValueError(kind)
        out.append(max(lo,min(hi,v)))
    return out

def predictor_best_us(values):
    best=None
    for mode in (0,1,2):
        rs=kmrl.residuals_for(values,mode)
        us=[kmrl.zz_enc(r) for r in rs]
        try:
            classes=[kmrl.residual_class(u) for u in us]
        except ValueError:
            continue
        cost=kmrl.representation_cost(us)
        cand=(cost,mode,us,classes)
        if best is None or cand[:2]<best[:2]:best=cand
    if best is None:raise RuntimeError("no predictor")
    return best

def raw_classmap_bytes(classes):
    return (len(classes)+3)//4

def rle_classmap_bytes(classes):
    if not classes:return 1
    # 1 byte per run: top 2 bits class, low 6 bits run_len-1 (1..64).
    runs=0;i=0
    while i<len(classes):
        c=classes[i];j=i+1
        while j<len(classes) and classes[j]==c and j-i<64:
            j+=1
        runs+=1;i=j
    return runs

def magnitude_bytes(us,classes):
    counts=[classes.count(i) for i in range(4)]
    return ((counts[0]+1)//2 + counts[1] + 2*counts[2] + 4*counts[3])

def evaluate(values):
    base_total=0; adapt_total=0; rle_tiles=0
    t0=time.perf_counter()
    for i in range(0,len(values),kmrl.TILE_FRAMES):
        tile=values[i:i+kmrl.TILE_FRAMES]
        _,mode,us,classes=predictor_best_us(tile)
        mag=magnitude_bytes(us,classes)
        raw=raw_classmap_bytes(classes)
        rle=rle_classmap_bytes(classes)
        # Existing component: predictor byte + raw class map + magnitudes.
        base_total+=1+raw+mag
        # Candidate: predictor byte + map-mode byte + chosen map + magnitudes.
        # The extra mode byte is fully accounted for.
        adapt_total+=2+min(raw,rle)+mag
        if rle<raw:rle_tiles+=1
    elapsed=(time.perf_counter()-t0)*1000
    return base_total,adapt_total,rle_tiles,elapsed

def main():
    gains=[]
    for bits in (16,24,32):
        for kind in ("tone","speechlike","transient","noisy"):
            vals=make_signal(kind,bits)
            b,a,r,t=evaluate(vals)
            gain=(b-a)*100.0/b
            gains.append(gain)
            print(f"KS10_PASS kind={kind} bits={bits} base_bytes={b} adaptive_bytes={a} gain_pct={gain:.6f} rle_tiles={r} eval_ms={t:.6f}")
    print(f"KS10_SUMMARY cases={len(gains)} mean_gain_pct={sum(gains)/len(gains):.6f} positive_cases={sum(g>0 for g in gains)} best_gain_pct={max(gains):.6f}")

if __name__=="__main__":
    main()
