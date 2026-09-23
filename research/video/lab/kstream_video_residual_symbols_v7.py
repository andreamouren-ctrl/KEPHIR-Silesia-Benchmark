#!/usr/bin/env python3
"""
KSV-07 residual-symbol representation experiment.

Motion search remains identical to MC8R4. The experiment changes only the
reversible symbol mapping of prediction residual bytes.

Modes:
  0 MOD8       : current modulo-256 residual bytes (baseline)
  1 ZZ_INTER   : ZigZag-fold only inter-frame motion residual bytes
  2 ZZ_ALL     : ZigZag-fold both intra spatial residuals and inter residuals

ZigZag/sign folding is BACKGROUND arithmetic. The experiment asks whether
feeding KHEPRI a zero-centered residual alphabet materially improves the
current AURORA video pipeline.
"""
import argparse, struct, zlib
from pathlib import Path

from kstream_video_baseline import frame_sizes
from kstream_video_motion_control import (
    spatial_frame, spatial_frame_inv,
    motion_residual, motion_inverse
)

MAGIC=b"KSR7"
VERSION=1
FMT_YUV420P8=1
HDR=struct.Struct("<4sBBBBBHHII")  # magic,ver,fmt,gop,block,mode,w,h,fpsn,fpsd
CHUNK=struct.Struct("<III")

MOD8=0
ZZ_INTER=1
ZZ_ALL=2

def zz_byte(b):
    s=b if b<128 else b-256
    return (s<<1) if s>=0 else ((-s<<1)-1)

def unzz_byte(z):
    s=(z>>1) if (z&1)==0 else -((z+1)>>1)
    return s & 255

def map_residual(buf,mode):
    if mode==MOD8: return buf
    return bytes(zz_byte(b) for b in buf)

def unmap_residual(buf,mode):
    if mode==MOD8: return buf
    return bytes(unzz_byte(b) for b in buf)

def encode_file(src:Path,dst:Path,w:int,h:int,fpsn:int,fpsd:int,
                gop:int=10,block:int=8,radius:int=4,mode:int=MOD8):
    if mode not in (MOD8,ZZ_INTER,ZZ_ALL): raise ValueError("bad residual mode")
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    if len(raw)%fs: raise ValueError("incomplete YUV frames")
    total=len(raw)//fs
    mvn=(w//block)*(h//block)

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,FMT_YUV420P8,gop,block,mode,w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(gop,total-off); payload=bytearray(); prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None:
                    res=spatial_frame(frame,w,h)
                    payload.extend(map_residual(res, ZZ_ALL if mode==ZZ_ALL else MOD8))
                else:
                    mv,res=motion_residual(frame,prev,w,h,block,radius)
                    if len(mv)!=mvn or len(res)!=fs: raise ValueError("internal size")
                    payload.extend(mv)
                    payload.extend(map_residual(res, ZZ_INTER if mode in (ZZ_INTER,ZZ_ALL) else MOD8))
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n

def decode_file(src:Path,dst:Path,radius:int=4):
    b=src.read_bytes()
    if len(b)<HDR.size: raise ValueError("truncated header")
    magic,ver,fmt,gop,block,mode,w,h,fpsn,fpsd=HDR.unpack_from(b,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT_YUV420P8 or mode not in (0,1,2):
        raise ValueError("unsupported stream")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    mvn=(w//block)*(h//block)
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
                mapped=p[q:q+fs]; q+=fs
                res=unmap_residual(mapped, ZZ_ALL if mode==ZZ_ALL else MOD8)
                frame=spatial_frame_inv(res,w,h)
            else:
                if q+mvn+fs>len(p): raise ValueError("truncated inter")
                mv=p[q:q+mvn]; q+=mvn
                mapped=p[q:q+fs]; q+=fs
                res=unmap_residual(mapped, ZZ_INTER if mode in (ZZ_INTER,ZZ_ALL) else MOD8)
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
    e.add_argument("--radius",type=int,default=4); e.add_argument("--mode",type=int,choices=(0,1,2),required=True)
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    d.add_argument("--radius",type=int,default=4)
    a=ap.parse_args()
    if a.cmd=="encode":
        encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.block,a.radius,a.mode)
    else:
        decode_file(a.src,a.dst,a.radius)

if __name__=="__main__": main()
