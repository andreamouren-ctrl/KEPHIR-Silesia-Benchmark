#!/usr/bin/env python3
"""
KMRL geometry laboratory.

Layouts:
  1 CARRY_PACKED       - KMRL-0 style fields, predictor history carried inside a chunk.
  2 FULL_256_PLANES    - residual bytes transposed into 256-position planes.
  3 CLASS_FULL_PLANES  - full planes plus an explicit 256-byte residual-class plane.
  4 FULL256_TAIL16     - promoted FULL256 geometry with 16-byte tail trimming.

All prediction state resets at the outer stream chunk boundary.
"""
import argparse
import struct
import zlib
from pathlib import Path

MAGIC = b"KRL2"
VERSION = 1
TILE = 256
HDR = struct.Struct("<4sBBBHIIQ")  # magic, version, layout, channels, bits, rate, block_ms, frames
CHUNK = struct.Struct("<III")


def zz_enc(v):
    return (v << 1) ^ (v >> 63)


def zz_dec(u):
    return (u >> 1) ^ -(u & 1)


def predict(mode, hist):
    n = len(hist)
    if mode == 0:
        return hist[-1] if n else 0
    if mode == 1:
        if n >= 2:
            return 2 * hist[-1] - hist[-2]
        return hist[-1] if n else 0
    if mode == 2:
        if n >= 3:
            return 3 * hist[-1] - 3 * hist[-2] + hist[-3]
        if n >= 2:
            return 2 * hist[-1] - hist[-2]
        return hist[-1] if n else 0
    raise ValueError("bad predictor")


def residuals(values, mode, initial_hist):
    hist = list(initial_hist[-3:])
    rs = []
    for x in values:
        p = predict(mode, hist)
        rs.append(x - p)
        hist.append(x)
        if len(hist) > 3:
            hist.pop(0)
    return rs


def rclass(u):
    if u < 16: return 0
    if u < 256: return 1
    if u < 65536: return 2
    if u < (1 << 32): return 3
    raise ValueError("residual too large")


def class_cost(us):
    cs = [rclass(u) for u in us]
    n = [cs.count(i) for i in range(4)]
    return (len(us) + 3) // 4 + (n[0] + 1) // 2 + n[1] + 2*n[2] + 4*n[3]


def choose(values, initial_hist):
    cands = []
    for mode in (0, 1, 2):
        us = [zz_enc(r) for r in residuals(values, mode, initial_hist)]
        # Selection stays independent from physical layout so the experiment
        # isolates serialization geometry rather than predictor heuristics.
        cands.append((class_cost(us), mode, us))
    return min(cands, key=lambda x: (x[0], x[1]))


def pack_classes(cs):
    out = bytearray((len(cs) + 3) // 4)
    for i, c in enumerate(cs):
        out[i//4] |= (c & 3) << (2*(i & 3))
    return out


def unpack_classes(buf, pos, n):
    need = (n + 3)//4
    if pos + need > len(buf):
        raise ValueError("truncated classes")
    b = buf[pos:pos+need]
    pos += need
    cs = [((b[i//4] >> (2*(i & 3))) & 3) for i in range(n)]
    return cs, pos


def enc_grouped(us):
    cs = [rclass(u) for u in us]
    out = bytearray(pack_classes(cs))
    pools = [[u for u,c in zip(us,cs) if c==k] for k in range(4)]

    p = pools[0]
    for i in range(0,len(p),2):
        out.append((p[i] & 15) | (((p[i+1] if i+1<len(p) else 0) & 15) << 4))

    out.extend(u & 255 for u in pools[1])
    out.extend(u & 255 for u in pools[2])
    out.extend((u>>8) & 255 for u in pools[2])
    for sh in (0,8,16,24):
        out.extend((u>>sh) & 255 for u in pools[3])
    return bytes(out)


def dec_grouped(buf, pos, n):
    cs, pos = unpack_classes(buf, pos, n)
    cnt = [cs.count(k) for k in range(4)]

    need = (cnt[0]+1)//2
    if pos+need > len(buf): raise ValueError("truncated c0")
    b0=buf[pos:pos+need]; pos+=need
    p0=[(b0[i//2]>>(4*(i&1)))&15 for i in range(cnt[0])]

    if pos+cnt[1] > len(buf): raise ValueError("truncated c1")
    p1=list(buf[pos:pos+cnt[1]]); pos+=cnt[1]

    if pos+2*cnt[2] > len(buf): raise ValueError("truncated c2")
    lo=buf[pos:pos+cnt[2]]; pos+=cnt[2]
    hi=buf[pos:pos+cnt[2]]; pos+=cnt[2]
    p2=[lo[i]|(hi[i]<<8) for i in range(cnt[2])]

    if pos+4*cnt[3] > len(buf): raise ValueError("truncated c3")
    planes=[]
    for _ in range(4):
        planes.append(buf[pos:pos+cnt[3]]); pos+=cnt[3]
    p3=[planes[0][i]|(planes[1][i]<<8)|(planes[2][i]<<16)|(planes[3][i]<<24)
        for i in range(cnt[3])]

    pools=[p0,p1,p2,p3]; idx=[0,0,0,0]; us=[]
    for c in cs:
        us.append(pools[c][idx[c]]); idx[c]+=1
    return us,pos


def plane_count(us):
    m=max(us, default=0)
    return max(1, (m.bit_length()+7)//8)


def enc_fullplanes(us, with_class):
    pc=plane_count(us)
    out=bytearray([pc])
    if with_class:
        cs=[rclass(u) for u in us]
        out.extend(cs)
        out.extend(b"\0"*(TILE-len(cs)))
    for sh in range(0,8*pc,8):
        out.extend((u>>sh)&255 for u in us)
        out.extend(b"\0"*(TILE-len(us)))
    return bytes(out)


def dec_fullplanes(buf,pos,n,with_class):
    if pos>=len(buf): raise ValueError("truncated plane count")
    pc=buf[pos];pos+=1
    if pc<1 or pc>4: raise ValueError("bad plane count")
    classes=None
    if with_class:
        if pos+TILE>len(buf): raise ValueError("truncated class plane")
        classes=list(buf[pos:pos+n]);pos+=TILE
    if pos+pc*TILE>len(buf): raise ValueError("truncated residual planes")
    planes=[]
    for _ in range(pc):
        planes.append(buf[pos:pos+TILE]);pos+=TILE
    us=[]
    for i in range(n):
        u=0
        for p in range(pc):
            u |= planes[p][i] << (8*p)
        if classes is not None and rclass(u)!=classes[i]:
            raise ValueError("class plane mismatch")
        us.append(u)
    return us,pos


def enc_tail16(us):
    """FULL256 plane layout with lossless 16-byte tail trimming."""
    pc=plane_count(us)
    out=bytearray([pc])
    n=len(us)
    for sh in range(0,8*pc,8):
        plane=bytearray((u>>sh)&255 for u in us)
        if n<TILE:
            plane.extend(b"\0"*(TILE-n))
        last=-1
        for i in range(TILE-1,-1,-1):
            if plane[i]:
                last=i
                break
        units=0 if last<0 else ((last+16)//16)
        if units>16:
            units=16
        out.append(units)
        out.extend(plane[:units*16])
    return bytes(out)


def dec_tail16(buf,pos,n):
    """Decode FULL256 TAIL16 planes and restore implicit zero tails."""
    if pos>=len(buf):
        raise ValueError("truncated plane count")
    pc=buf[pos]; pos+=1
    if pc<1 or pc>4:
        raise ValueError("bad plane count")
    planes=[]
    for _ in range(pc):
        if pos>=len(buf):
            raise ValueError("truncated tail16 length")
        units=buf[pos]; pos+=1
        if units>16:
            raise ValueError("bad tail16 units")
        take=units*16
        if pos+take>len(buf):
            raise ValueError("truncated tail16 plane")
        plane=bytearray(TILE)
        plane[:take]=buf[pos:pos+take]
        pos+=take
        planes.append(plane)
    us=[]
    for i in range(n):
        u=0
        for p in range(pc):
            u |= planes[p][i] << (8*p)
        us.append(u)
    return us,pos


def components(samples,channels):
    if channels==2:
        a=[];b=[]
        for i in range(0,len(samples),2):
            l,r=samples[i],samples[i+1]
            s=l-r; m=r+(s>>1)
            a.append(m);b.append(s)
        return [a,b]
    out=[[] for _ in range(channels)]
    for i,x in enumerate(samples): out[i%channels].append(x)
    return out


def merge(comps,channels):
    if channels==2:
        out=[]
        for m,s in zip(comps[0],comps[1]):
            r=m-(s>>1); l=s+r
            if not(-32768<=l<=32767 and -32768<=r<=32767): raise ValueError("range")
            out.extend((l,r))
        return out
    out=[]
    for i in range(len(comps[0])):
        for c in range(channels):
            x=comps[c][i]
            if not -32768<=x<=32767: raise ValueError("range")
            out.append(x)
    return out


def encode_payload(samples,channels,frames,layout):
    out=bytearray()
    comps=components(samples,channels)
    histories=[[] for _ in range(channels)]
    frame0=0
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            vals=comps[c][frame0:frame0+n]
            _,mode,us=choose(vals,histories[c])
            out.append(mode)
            if layout==1:
                out.extend(enc_grouped(us))
            elif layout==2:
                out.extend(enc_fullplanes(us,False))
            elif layout==3:
                out.extend(enc_fullplanes(us,True))
            elif layout==4:
                out.extend(enc_tail16(us))
            else:
                raise ValueError("bad layout")
            histories[c].extend(vals)
            histories[c]=histories[c][-3:]
        frame0+=n
    return bytes(out)


def decode_payload(payload,channels,frames,layout):
    pos=0; frame0=0
    histories=[[] for _ in range(channels)]
    compout=[[] for _ in range(channels)]
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            if pos>=len(payload): raise ValueError("truncated mode")
            mode=payload[pos];pos+=1
            if mode not in (0,1,2): raise ValueError("bad mode")
            if layout==1:
                us,pos=dec_grouped(payload,pos,n)
            elif layout==2:
                us,pos=dec_fullplanes(payload,pos,n,False)
            elif layout==3:
                us,pos=dec_fullplanes(payload,pos,n,True)
            elif layout==4:
                us,pos=dec_tail16(payload,pos,n)
            else:
                raise ValueError("bad layout")
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
    if pos!=len(payload): raise ValueError("trailing payload")
    return merge(compout,channels)


def encode_file(src:Path,dst:Path,channels:int,rate:int,block_ms:int,layout:int):
    raw=src.read_bytes(); fb=2*channels
    if channels<1 or len(raw)%fb: raise SystemExit("bad PCM")
    total=len(raw)//fb; block=max(1,rate*block_ms//1000)
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,layout,channels,16,rate,block_ms,total))
        off=0
        while off<total:
            n=min(block,total-off)
            b=raw[off*fb:(off+n)*fb]
            samples=list(struct.unpack("<"+"h"*(n*channels),b))
            p=encode_payload(samples,channels,n,layout)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff));f.write(p)
            off+=n


def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size: raise SystemExit("truncated")
    magic,ver,layout,ch,bits,rate,bms,total=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or layout not in (1,2,3,4) or bits!=16: raise SystemExit("unsupported")
    pos=HDR.size;got=0;out=bytearray()
    while got<total:
        if pos+CHUNK.size>len(data): raise SystemExit("truncated chunk")
        n,sz,crc=CHUNK.unpack_from(data,pos);pos+=CHUNK.size
        if n<1 or got+n>total or pos+sz>len(data): raise SystemExit("bad chunk")
        p=data[pos:pos+sz];pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise SystemExit("crc")
        vals=decode_payload(p,ch,n,layout)
        out.extend(struct.pack("<"+"h"*len(vals),*vals));got+=n
    if pos!=len(data): raise SystemExit("trailing")
    dst.write_bytes(out)


def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode");e.add_argument("src",type=Path);e.add_argument("dst",type=Path)
    e.add_argument("--channels",type=int,required=True);e.add_argument("--rate",type=int,required=True)
    e.add_argument("--block-ms",type=int,default=20);e.add_argument("--layout",type=int,choices=(1,2,3,4),required=True)
    d=sp.add_parser("decode");d.add_argument("src",type=Path);d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.channels,a.rate,a.block_ms,a.layout)
    else: decode_file(a.src,a.dst)


if __name__=="__main__":
    main()
