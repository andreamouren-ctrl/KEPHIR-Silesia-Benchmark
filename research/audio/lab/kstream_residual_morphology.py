#!/usr/bin/env python3
"""
KS-06 residual morphology laboratory.

These sign/magnitude layouts are BACKGROUND research controls, not patent claims.
The goal is to learn what representation EXP-33H responds to before designing
a genuinely KHEPRI-specific residual model.
"""
import argparse
import struct
import zlib
from pathlib import Path

from kstream_kmrl_lab import zz_dec, predict, choose, components, merge

MAGIC=b"KRM1"
VERSION=1
TILE=256
HDR=struct.Struct("<4sBBBHIIQ")
CHUNK=struct.Struct("<III")


def pack_bits(bits):
    out=bytearray((len(bits)+7)//8)
    for i,b in enumerate(bits):
        if b: out[i//8] |= 1 << (i&7)
    return bytes(out)


def unpack_bits(buf,pos,n):
    need=(n+7)//8
    if pos+need>len(buf): raise ValueError("truncated bit field")
    raw=buf[pos:pos+need]; pos+=need
    return [1 if raw[i//8]&(1<<(i&7)) else 0 for i in range(n)],pos


def residuals_from_us(us):
    return [zz_dec(u) for u in us]


def magnitude_planes(rs):
    mags=[abs(r) for r in rs]
    m=max(mags,default=0)
    pc=max(1,(m.bit_length()+7)//8)
    if pc>4: raise ValueError("magnitude too large")
    planes=[]
    for sh in range(0,pc*8,8):
        p=bytearray(TILE)
        for i,v in enumerate(mags):
            p[i]=(v>>sh)&255
        planes.append(bytes(p))
    return planes


def signs_for(rs):
    return [1 if r<0 else 0 for r in rs]


def transition_signs(signs):
    out=[]
    prev=0
    for s in signs:
        out.append(s^prev)
        prev=s
    return out


def restore_transition(bits):
    out=[]
    prev=0
    for b in bits:
        s=b^prev
        out.append(s)
        prev=s
    return out


def encode_tile(values,hist,layout):
    # Predictor selection intentionally remains the same as KMRL1 FULL256.
    _,mode,us=choose(values,hist)
    rs=residuals_from_us(us)
    planes=magnitude_planes(rs)
    signs=signs_for(rs)

    out=bytearray((mode,len(planes)))
    for p in planes:
        out.extend(p)

    if layout==1:              # packed signs
        out.extend(pack_bits(signs))
    elif layout==2:            # 256-byte sign plane
        out.extend(bytes(signs))
        out.extend(b"\0"*(TILE-len(signs)))
    elif layout==3:            # packed transition signs
        out.extend(pack_bits(transition_signs(signs)))
    else:
        raise ValueError("bad layout")
    return bytes(out)


def decode_tile(buf,pos,n,hist,layout):
    if pos+2>len(buf): raise ValueError("truncated tile header")
    mode,pc=buf[pos],buf[pos+1];pos+=2
    if mode not in (0,1,2) or pc<1 or pc>4: raise ValueError("bad tile header")

    if pos+pc*TILE>len(buf): raise ValueError("truncated magnitude planes")
    planes=[]
    for _ in range(pc):
        planes.append(buf[pos:pos+TILE]);pos+=TILE

    if layout==1:
        signs,pos=unpack_bits(buf,pos,n)
    elif layout==2:
        if pos+TILE>len(buf): raise ValueError("truncated sign plane")
        signs=list(buf[pos:pos+n]);pos+=TILE
        if any(s not in (0,1) for s in signs): raise ValueError("bad sign")
    elif layout==3:
        trans,pos=unpack_bits(buf,pos,n)
        signs=restore_transition(trans)
    else:
        raise ValueError("bad layout")

    vals=[]
    local=list(hist[-3:])
    for i in range(n):
        mag=0
        for k,p in enumerate(planes):
            mag |= p[i] << (8*k)
        r=-mag if signs[i] and mag else mag
        x=predict(mode,local)+r
        vals.append(x)
        local.append(x)
        if len(local)>3: local.pop(0)
    return vals,pos


def encode_payload(samples,channels,frames,layout):
    comps=components(samples,channels)
    histories=[[] for _ in range(channels)]
    out=bytearray()
    frame0=0
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            vals=comps[c][frame0:frame0+n]
            out.extend(encode_tile(vals,histories[c],layout))
            histories[c].extend(vals)
            histories[c]=histories[c][-3:]
        frame0+=n
    return bytes(out)


def decode_payload(payload,channels,frames,layout):
    histories=[[] for _ in range(channels)]
    compout=[[] for _ in range(channels)]
    pos=0;frame0=0
    while frame0<frames:
        n=min(TILE,frames-frame0)
        for c in range(channels):
            vals,pos=decode_tile(payload,pos,n,histories[c],layout)
            histories[c].extend(vals)
            histories[c]=histories[c][-3:]
            compout[c].extend(vals)
        frame0+=n
    if pos!=len(payload): raise ValueError("trailing payload")
    return merge(compout,channels)


def encode_file(src:Path,dst:Path,channels:int,rate:int,block_ms:int,layout:int):
    raw=src.read_bytes(); fb=2*channels
    if layout not in (1,2,3) or channels<1 or len(raw)%fb: raise SystemExit("bad PCM")
    total=len(raw)//fb; block=max(1,rate*block_ms//1000)
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,layout,channels,16,rate,block_ms,total))
        off=0
        while off<total:
            n=min(block,total-off)
            b=raw[off*fb:(off+n)*fb]
            samples=list(struct.unpack("<"+"h"*(n*channels),b))
            p=encode_payload(samples,channels,n,layout)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n


def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size: raise SystemExit("truncated")
    magic,ver,layout,ch,bits,rate,bms,total=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or layout not in (1,2,3) or bits!=16: raise SystemExit("unsupported")
    pos=HDR.size; got=0; out=bytearray()
    while got<total:
        if pos+CHUNK.size>len(data): raise SystemExit("truncated chunk")
        n,sz,crc=CHUNK.unpack_from(data,pos); pos+=CHUNK.size
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
    e=sp.add_parser("encode"); e.add_argument("src",type=Path); e.add_argument("dst",type=Path)
    e.add_argument("--channels",type=int,required=True); e.add_argument("--rate",type=int,required=True)
    e.add_argument("--block-ms",type=int,default=20); e.add_argument("--layout",type=int,choices=(1,2,3),required=True)
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.channels,a.rate,a.block_ms,a.layout)
    else: decode_file(a.src,a.dst)


if __name__=="__main__":
    main()
