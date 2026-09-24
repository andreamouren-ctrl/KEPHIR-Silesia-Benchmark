#!/usr/bin/env python3
from pathlib import Path

def parse(path):
    out={}
    for line in Path(path).read_text().splitlines():
        if not line.startswith("TILE_STAT "): continue
        d={}
        for token in line.split()[1:]:
            k,v=token.split("=",1); d[k]=v
        key=(d["name"],int(d["tile"]))
        out[key]=dict(
            mean=float(d["mean"]),
            zero_pct=float(d["zero_pct"]),
            us=float(d["encode_us"]),
            packed=int(d["packed"]),
            raw=int(d["raw"]),
        )
    return out

e=parse("tile_exp37.txt")
f=parse("tile_fastd.txt")
if set(e)!=set(f):
    raise SystemExit("TILE_KEY_MISMATCH")

thresholds=[0.5,1.0,1.5,2.0,2.6,3.5,5.0,8.0,12.0,20.0]
names=["1080p","1440p","4K"]

for name in names:
    keys=sorted(k for k in e if k[0]==name)
    exp_bytes=sum(e[k]["packed"] for k in keys)
    fast_bytes=sum(f[k]["packed"] for k in keys)
    exp_us=sum(e[k]["us"] for k in keys)
    fast_us=sum(f[k]["us"] for k in keys)
    print(f"ROUTER_BASE name={name} exp_bytes={exp_bytes} fast_bytes={fast_bytes} exp_us={exp_us:.3f} fast_us={fast_us:.3f}")
    for th in thresholds:
        # Low-magnitude residuals use FAST-D; harder tiles keep EXP-37A.
        use_fast=[k for k in keys if e[k]["mean"]<=th]
        fastset=set(use_fast)
        rb=sum((f[k] if k in fastset else e[k])["packed"] for k in keys)
        ru=sum((f[k] if k in fastset else e[k])["us"] for k in keys)
        fast_pct=100.0*len(use_fast)/len(keys)
        byte_pen=100.0*(rb-exp_bytes)/exp_bytes if exp_bytes else 0.0
        speedup=exp_us/ru if ru else 0.0
        print(f"ROUTER_SIM name={name} threshold={th} fast_tiles_pct={fast_pct:.3f} bytes={rb} byte_penalty_pct={byte_pen:.4f} cpu_us={ru:.3f} speedup_x={speedup:.4f}")
