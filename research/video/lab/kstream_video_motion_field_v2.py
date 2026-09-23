#!/usr/bin/env python3
"""
KSV-06 motion-field representation experiment.

The motion search and residual are identical to the existing MC8R4 control.
Only the reversible representation of the motion field changes:

  mode 0 RAW8      : one candidate index byte per block (baseline)
  mode 1 INDEX5    : candidate index packed to 5 bits
  mode 2 XY3_SPLIT : dx and dy represented as separate 3-bit code planes

Generic bit packing and motion-vector coding are BACKGROUND engineering.
The research question is whether a KHEPRI-friendly separation of motion-field
coordinates improves final backend compression.
"""
import argparse, struct, zlib
from pathlib import Path

from kstream_video_baseline import frame_sizes
from kstream_video_motion_control import candidates, motion_residual, motion_inverse, spatial_frame, spatial_frame_inv

MAGIC=b"KSM2"
VERSION=1
FMT_YUV420P8=1
HDR=struct.Struct("<4sBBBBBBHHII")  # magic,ver,fmt,gop,block,radius,mapmode,w,h,fpsn,fpsd
CHUNK=struct.Struct("<III")

RAW8=0
INDEX5=1
XY3_SPLIT=2

def pack_bits(vals,bits):
    out=bytearray((len(vals)*bits+7)//8)
    bitpos=0
    mask=(1<<bits)-1
    for v in vals:
        if v<0 or v>mask: raise ValueError("value out of range")
        byte=bitpos>>3; shift=bitpos&7
        x=v<<shift
        out[byte] |= x & 0xff
        if shift+bits>8:
            out[byte+1] |= (x>>8)&0xff
        bitpos+=bits
    return bytes(out)

def unpack_bits(buf,count,bits):
    vals=[]; bitpos=0; mask=(1<<bits)-1
    for _ in range(count):
        byte=bitpos>>3; shift=bitpos&7
        if byte>=len(buf): raise ValueError("truncated bit field")
        x=buf[byte]>>shift
        if shift+bits>8:
            if byte+1>=len(buf): raise ValueError("truncated bit field")
            x |= buf[byte+1]<<(8-shift)
        vals.append(x&mask)
        bitpos+=bits
    return vals

def map_size(count,mode):
    if mode==RAW8: return count
    if mode==INDEX5: return (count*5+7)//8
    if mode==XY3_SPLIT: return 2*((count*3+7)//8)
    raise ValueError("bad map mode")

def encode_map(mv,mode,radius):
    if mode==RAW8: return mv
    vals=list(mv)
    cand=candidates(radius)
    if mode==INDEX5:
        return pack_bits(vals,5)
    if mode==XY3_SPLIT:
        xs=[]; ys=[]
        for idx in vals:
            if idx>=len(cand): raise ValueError("bad motion index")
            dx,dy=cand[idx]
            xs.append((dx+radius)//2)
            ys.append((dy+radius)//2)
        return pack_bits(xs,3)+pack_bits(ys,3)
    raise ValueError("bad map mode")

def decode_map(buf,count,mode,radius):
    if mode==RAW8:
        if len(buf)!=count: raise ValueError("bad raw map")
        return bytes(buf)
    cand=candidates(radius)
    if mode==INDEX5:
        vals=unpack_bits(buf,count,5)
        if any(v>=len(cand) for v in vals): raise ValueError("bad packed motion index")
        return bytes(vals)
    if mode==XY3_SPLIT:
        part=(count*3+7)//8
        if len(buf)!=2*part: raise ValueError("bad xy map")
        xs=unpack_bits(buf[:part],count,3)
        ys=unpack_bits(buf[part:],count,3)
        lookup={p:i for i,p in enumerate(cand)}
        out=bytearray()
        for x,y in zip(xs,ys):
            dx=x*2-radius; dy=y*2-radius
            idx=lookup.get((dx,dy))
            if idx is None: raise ValueError("invalid xy vector")
            out.append(idx)
        return bytes(out)
    raise ValueError("bad map mode")

def encode_file(src:Path,dst:Path,w:int,h:int,fpsn:int,fpsd:int,
                gop:int,block:int,radius:int,map_mode:int):
    if block not in (8,16) or radius not in (2,4,6):
        raise ValueError("unsupported geometry")
    if w%block or h%block: raise ValueError("frame not divisible by block")
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    if len(raw)%fs: raise ValueError("incomplete YUV frames")
    total=len(raw)//fs
    mvn=(w//block)*(h//block)

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,FMT_YUV420P8,gop,block,radius,map_mode,w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(gop,total-off); payload=bytearray(); prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None:
                    payload.extend(spatial_frame(frame,w,h))
                else:
                    mv,res=motion_residual(frame,prev,w,h,block,radius)
                    mapped=encode_map(mv,map_mode,radius)
                    if len(mapped)!=map_size(mvn,map_mode): raise ValueError("map size")
                    payload.extend(mapped); payload.extend(res)
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n

def decode_file(src:Path,dst:Path):
    b=src.read_bytes()
    if len(b)<HDR.size: raise ValueError("truncated header")
    magic,ver,fmt,gop,block,radius,map_mode,w,h,fpsn,fpsd=HDR.unpack_from(b,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT_YUV420P8 or map_mode not in (0,1,2):
        raise ValueError("unsupported stream")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    mvn=(w//block)*(h//block); msz=map_size(mvn,map_mode)
    pos=HDR.size; out=bytearray()
    while pos<len(b):
        if pos+CHUNK.size>len(b): raise ValueError("truncated chunk")
        n,sz,crc=CHUNK.unpack_from(b,pos); pos+=CHUNK.size
        if n<1 or n>gop or pos+sz>len(b): raise ValueError("bad chunk")
        p=b[pos:pos+sz]; pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise ValueError("crc")
        q=0; prev=None
        for _ in range(n):
            if prev is None:
                if q+fs>len(p): raise ValueError("truncated intra")
                frame=spatial_frame_inv(p[q:q+fs],w,h); q+=fs
            else:
                if q+msz+fs>len(p): raise ValueError("truncated inter")
                mv=decode_map(p[q:q+msz],mvn,map_mode,radius); q+=msz
                res=p[q:q+fs]; q+=fs
                frame=motion_inverse(mv,res,prev,w,h,block,radius)
            out.extend(frame); prev=frame
        if q!=len(p): raise ValueError("trailing chunk data")
    dst.write_bytes(out)

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode"); e.add_argument("src",type=Path); e.add_argument("dst",type=Path)
    e.add_argument("--width",type=int,required=True); e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,required=True); e.add_argument("--fps-den",type=int,required=True)
    e.add_argument("--gop",type=int,default=10); e.add_argument("--block",type=int,default=8)
    e.add_argument("--radius",type=int,default=4); e.add_argument("--map-mode",type=int,choices=(0,1,2),required=True)
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode":
        encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.block,a.radius,a.map_mode)
    else:
        decode_file(a.src,a.dst)

if __name__=="__main__": main()
