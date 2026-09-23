#!/usr/bin/env python3
"""
KTARP-0 — KHEPRI Topology-Adaptive Residual Permutation research codec.

Candidate-IP experiment: dynamically choose a reversible 16x16 arrangement
using an affinity function derived from EXP-33H's favored distance
neighborhoods. Fixed predictors/byte planes are background techniques.
"""
import argparse
import struct
import zlib
from pathlib import Path

from kstream_kmrl_lab import zz_enc, zz_dec, predict, choose, components, merge

MAGIC=b"KTA1"
VERSION=1
TILE=256
HDR=struct.Struct("<4sBBBHIIQ")  # magic, version, strategy, channels, bits, rate, block_ms, frames
CHUNK=struct.Struct("<III")

# Source is row-major 16x16. Each permutation lists source indices in serialized order.
PERMS=[]
PERMS.append(list(range(TILE)))
PERMS.append([c*16+r for r in range(16) for c in range(16)])
PERMS.append([r*16+(c if r%2==0 else 15-c) for r in range(16) for c in range(16)])
PERMS.append([(r if c%2==0 else 15-r)*16+c for c in range(16) for r in range(16)])

INVERSE=[]
for p in PERMS:
    inv=[0]*TILE
    for out_i,src_i in enumerate(p):
        inv[src_i]=out_i
    INVERSE.append(inv)

DIST_WEIGHTS=((15,3),(16,5),(17,3),(255,2),(256,6),(257,2))


def make_planes(us):
    m=max(us,default=0)
    pc=max(1,(m.bit_length()+7)//8)
    planes=[]
    for sh in range(0,8*pc,8):
        b=bytearray(TILE)
        for i,u in enumerate(us):
            b[i]=(u>>sh)&255
        planes.append(bytes(b))
    return planes


def permute_plane(plane,pid):
    p=PERMS[pid]
    return bytes(plane[i] for i in p)


def unpermute_plane(serial,pid):
    inv=INVERSE[pid]
    # source position i is found at serialized position inv[i]
    return bytes(serial[inv[i]] for i in range(TILE))


def affinity_equal(blob):
    total=0
    n=len(blob)
    for d,w in DIST_WEIGHTS:
        if d>=n: continue
        total += w*sum(a==b for a,b in zip(blob[d:],blob[:-d]))
    return total


def affinity_run(blob):
    total=0
    n=len(blob)
    for d,w in DIST_WEIGHTS:
        if d>=n: continue
        eq=[a==b for a,b in zip(blob[d:],blob[:-d])]
        singles=sum(eq)
        pairs=sum(eq[i] and eq[i-1] for i in range(1,len(eq)))
        triples=sum(eq[i] and eq[i-1] and eq[i-2] for i in range(2,len(eq)))
        total += w*(singles + 2*pairs + 3*triples)
    return total


def choose_perm(planes,strategy):
    if strategy==0:
        return 1  # fixed transpose control
    best=(None,0)
    for pid in range(4):
        blob=b"".join(permute_plane(p,pid) for p in planes)
        score=affinity_equal(blob) if strategy==1 else affinity_run(blob)
        cand=(score,-pid)
        if best[0] is None or cand>best[0]:
            best=(cand,pid)
    return best[1]


def encode_payload(samples,channels,frames,strategy):
    comps=components(samples,channels)
    histories=[[] for _ in range(channels)]
    out=bytearray()
    frame0=0
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            vals=comps[c][frame0:frame0+n]
            _,mode,us=choose(vals,histories[c])
            planes=make_planes(us)
            pid=choose_perm(planes,strategy)
            out.extend((mode,len(planes),pid))
            for p in planes:
                out.extend(permute_plane(p,pid))
            histories[c].extend(vals)
            histories[c]=histories[c][-3:]
        frame0+=n
    return bytes(out)


def decode_payload(payload,channels,frames):
    pos=0;frame0=0
    histories=[[] for _ in range(channels)]
    compout=[[] for _ in range(channels)]
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            if pos+3>len(payload): raise ValueError("truncated KTARP header")
            mode,pc,pid=payload[pos],payload[pos+1],payload[pos+2];pos+=3
            if mode not in (0,1,2) or pc<1 or pc>4 or pid>3: raise ValueError("bad KTARP header")
            if pos+pc*TILE>len(payload): raise ValueError("truncated KTARP planes")
            planes=[]
            for _ in range(pc):
                serial=payload[pos:pos+TILE];pos+=TILE
                planes.append(unpermute_plane(serial,pid))
            us=[]
            for i in range(n):
                u=0
                for k,p in enumerate(planes):
                    u |= p[i]<<(8*k)
                us.append(u)
            hist=list(histories[c])
            vals=[]
            for u in us:
                x=predict(mode,hist)+zz_dec(u)
                vals.append(x)
                hist.append(x)
                if len(hist)>3: hist.pop(0)
            histories[c]=hist[-3:]
            compout[c].extend(vals)
        frame0+=n
    if pos!=len(payload): raise ValueError("trailing KTARP payload")
    return merge(compout,channels)


def encode_file(src:Path,dst:Path,channels:int,rate:int,block_ms:int,strategy:int):
    raw=src.read_bytes();fb=2*channels
    if strategy not in (0,1,2) or channels<1 or len(raw)%fb: raise SystemExit("bad input")
    total=len(raw)//fb;block=max(1,rate*block_ms//1000)
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,strategy,channels,16,rate,block_ms,total))
        off=0
        while off<total:
            n=min(block,total-off)
            b=raw[off*fb:(off+n)*fb]
            vals=list(struct.unpack("<"+"h"*(n*channels),b))
            p=encode_payload(vals,channels,n,strategy)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff));f.write(p)
            off+=n


def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size: raise SystemExit("truncated")
    magic,ver,strategy,ch,bits,rate,bms,total=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or strategy not in (0,1,2) or bits!=16: raise SystemExit("unsupported")
    pos=HDR.size;got=0;out=bytearray()
    while got<total:
        if pos+CHUNK.size>len(data): raise SystemExit("truncated chunk")
        n,sz,crc=CHUNK.unpack_from(data,pos);pos+=CHUNK.size
        if n<1 or got+n>total or pos+sz>len(data): raise SystemExit("bad chunk")
        p=data[pos:pos+sz];pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise SystemExit("crc")
        vals=decode_payload(p,ch,n)
        out.extend(struct.pack("<"+"h"*len(vals),*vals));got+=n
    if pos!=len(data): raise SystemExit("trailing")
    dst.write_bytes(out)


def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode");e.add_argument("src",type=Path);e.add_argument("dst",type=Path)
    e.add_argument("--channels",type=int,required=True);e.add_argument("--rate",type=int,required=True)
    e.add_argument("--block-ms",type=int,default=20);e.add_argument("--strategy",type=int,choices=(0,1,2),required=True)
    d=sp.add_parser("decode");d.add_argument("src",type=Path);d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.channels,a.rate,a.block_ms,a.strategy)
    else: decode_file(a.src,a.dst)


if __name__=="__main__":
    main()
