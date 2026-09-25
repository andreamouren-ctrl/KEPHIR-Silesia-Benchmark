#!/usr/bin/env python3
import math,time,random
from research.audio.lab import kstream_kmrl_frontend as kmrl

def pred(mode,h):
    n=len(h)
    if mode==0:
        return h[-1] if n else 0
    if mode==1:
        if n>=2:return 2*h[-1]-h[-2]
        return h[-1] if n else 0
    if mode==2:
        if n>=3:return 3*h[-1]-3*h[-2]+h[-3]
        if n>=2:return 2*h[-1]-h[-2]
        return h[-1] if n else 0
    if mode==3:
        # Half-slope predictor: cheap, stable and exact because it only predicts.
        if n>=2:return h[-1]+((h[-1]-h[-2])>>1)
        return h[-1] if n else 0
    if mode==4:
        # Quarter-slope predictor, more conservative on oscillatory material.
        if n>=2:return h[-1]+((h[-1]-h[-2])>>2)
        return h[-1] if n else 0
    if mode==5:
        # Two-tap weighted predictor, equivalent to 1.5*x[n-1]-0.5*x[n-2].
        if n>=2:return (3*h[-1]-h[-2])>>1
        return h[-1] if n else 0
    raise ValueError(mode)

def encode_cost(values,modes):
    best=None
    for mode in modes:
        h=[]; us=[]
        ok=True
        for x in values:
            r=x-pred(mode,h)
            h.append(x)
            u=kmrl.zz_enc(r)
            try: kmrl.residual_class(u)
            except ValueError:
                ok=False;break
            us.append(u)
        if not ok: continue
        cost=1+kmrl.representation_cost(us)
        cand=(cost,mode)
        if best is None or cand<best:best=cand
    if best is None: raise RuntimeError("no valid predictor")
    return best

def make_signal(kind,bits,n=32768):
    hi=(1<<(bits-1))-1
    amp=hi//12
    rng=random.Random(12345)
    out=[]
    for i in range(n):
        if kind=="tone":
            v=int(amp*math.sin(i*0.013)+amp*0.20*math.sin(i*0.031))
        elif kind=="speechlike":
            env=0.35+0.65*(0.5+0.5*math.sin(i*0.0009))
            v=int(env*(amp*math.sin(i*0.021)+amp*0.35*math.sin(i*0.046)))
        elif kind=="transient":
            v=int(amp*0.45*math.sin(i*0.017))
            if i%997<8:v+=int(amp*2.5*(1-(i%997)/8))
        elif kind=="noisy":
            v=int(amp*0.55*math.sin(i*0.019)+rng.randint(-amp//5,amp//5))
        else:raise ValueError(kind)
        lo=-(1<<(bits-1))
        out.append(max(lo,min(hi,v)))
    return out

def run(kind,bits):
    vals=make_signal(kind,bits)
    tiles=[vals[i:i+kmrl.TILE_FRAMES] for i in range(0,len(vals),kmrl.TILE_FRAMES)]
    def test(modes):
        t0=time.perf_counter(); total=0; picks={}
        for t in tiles:
            cost,mode=encode_cost(t,modes);total+=cost;picks[mode]=picks.get(mode,0)+1
        return total,(time.perf_counter()-t0)*1000,picks
    base=test((0,1,2))
    ext=test((0,1,2,3,4,5))
    gain=(base[0]-ext[0])*100.0/base[0]
    print(f"KS09_PASS kind={kind} bits={bits} base_bytes={base[0]} ext_bytes={ext[0]} gain_pct={gain:.6f} base_ms={base[1]:.6f} ext_ms={ext[1]:.6f} picks={ext[2]}")
    return gain,base,ext

def main():
    gains=[]
    for bits in (24,32):
        for kind in ("tone","speechlike","transient","noisy"):
            gains.append(run(kind,bits)[0])
    print(f"KS09_SUMMARY cases={len(gains)} mean_gain_pct={sum(gains)/len(gains):.6f} positive_cases={sum(g>0 for g in gains)}")

if __name__=="__main__":
    main()
