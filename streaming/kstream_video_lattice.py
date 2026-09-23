#!/usr/bin/env python3
"""
KSV-LATTICE control frontend.

Reversible block-major serialization of motion-compensated residuals.
This is a technical control. Fixed block/raster reordering is BACKGROUND
and is not claimed as candidate IP.
"""
import argparse
import struct
import zlib
from pathlib import Path

from kstream_video_baseline import frame_sizes, spatial_frame if False else frame_sizes
from kstream_video_baseline import plane_spatial, plane_spatial_inv, split_frame, join_frame
from kstream_video_mc import motion_residual, motion_inverse

MAGIC=b"KSL1"
VERSION=1
FMT_YUV420P8=1
HDR=struct.Struct("<4sBBBBBHHII")
CHUNK=struct.Struct("<III")


def blockize_plane(buf: bytes, w: int, h: int, b: int) -> bytes:
    if w % b or h % b:
        raise ValueError("plane not divisible by block")
    out=bytearray()
    mv=memoryview(buf)
    for by in range(0,h,b):
        for bx in range(0,w,b):
            for y in range(b):
                start=(by+y)*w+bx
                out.extend(mv[start:start+b])
    return bytes(out)


def unblockize_plane(buf: bytes, w: int, h: int, b: int) -> bytes:
    if w % b or h % b:
        raise ValueError("plane not divisible by block")
    if len(buf)!=w*h:
        raise ValueError("bad plane size")
    out=bytearray(w*h)
    pos=0
    for by in range(0,h,b):
        for bx in range(0,w,b):
            for y in range(b):
                start=(by+y)*w+bx
                out[start:start+b]=buf[pos:pos+b]
                pos+=b
    return bytes(out)


def blockize_residual(res: bytes, w: int, h: int, block: int) -> bytes:
    ys,cs,cw,ch=frame_sizes(w,h)
    y=res[:ys]
    u=res[ys:ys+cs]
    v=res[ys+cs:]
    cb=block//2
    return (blockize_plane(y,w,h,block)
            + blockize_plane(u,cw,ch,cb)
            + blockize_plane(v,cw,ch,cb))


def unblockize_residual(res: bytes, w: int, h: int, block: int) -> bytes:
    ys,cs,cw,ch=frame_sizes(w,h)
    y=res[:ys]
    u=res[ys:ys+cs]
    v=res[ys+cs:]
    cb=block//2
    return (unblockize_plane(y,w,h,block)
            + unblockize_plane(u,cw,ch,cb)
            + unblockize_plane(v,cw,ch,cb))


def spatial_frame(frame,w,h):
    y,u,v,cw,ch=split_frame(frame,w,h)
    return join_frame(plane_spatial(y,w,h,2),
                      plane_spatial(u,cw,ch,2),
                      plane_spatial(v,cw,ch,2))


def spatial_frame_inv(res,w,h):
    y,u,v,cw,ch=split_frame(res,w,h)
    return join_frame(plane_spatial_inv(y,w,h,2),
                      plane_spatial_inv(u,cw,ch,2),
                      plane_spatial_inv(v,cw,ch,2))


def encode_file(src:Path,dst:Path,w:int,h:int,fpsn:int,fpsd:int,gop:int,block:int,radius:int):
    if block not in (8,16) or radius not in (2,4,6) or radius%2:
        raise ValueError("unsupported control geometry")
    if w%block or h%block:
        raise ValueError("frame not divisible by block")
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h)
    fs=ys+2*cs
    if len(raw)%fs:
        raise SystemExit("input is not complete yuv420p frames")
    total=len(raw)//fs
    mvn=(w//block)*(h//block)

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,FMT_YUV420P8,gop,block,radius,w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(gop,total-off)
            payload=bytearray()
            prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None:
                    # Keep GOP recovery frame unchanged from KSV-MC control.
                    payload.extend(spatial_frame(frame,w,h))
                else:
                    mv,res=motion_residual(frame,prev,w,h,block,radius)
                    if len(mv)!=mvn or len(res)!=fs:
                        raise ValueError("internal size")
                    payload.extend(mv)
                    payload.extend(blockize_residual(res,w,h,block))
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff))
            f.write(p)
            off+=n


def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size:
        raise SystemExit("truncated header")
    magic,ver,fmt,gop,block,radius,w,h,fpsn,fpsd=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT_YUV420P8:
        raise SystemExit("unsupported stream")

    ys,cs,_,_=frame_sizes(w,h)
    fs=ys+2*cs
    mvn=(w//block)*(h//block)
    pos=HDR.size
    out=bytearray()

    while pos<len(data):
        if pos+CHUNK.size>len(data):
            raise SystemExit("truncated chunk header")
        n,sz,crc=CHUNK.unpack_from(data,pos)
        pos+=CHUNK.size
        if n<1 or n>gop or pos+sz>len(data):
            raise SystemExit("bad chunk")
        p=data[pos:pos+sz]
        pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc:
            raise SystemExit("crc")

        q=0
        prev=None
        for j in range(n):
            if prev is None:
                if q+fs>len(p):
                    raise SystemExit("truncated intra")
                frame=spatial_frame_inv(p[q:q+fs],w,h)
                q+=fs
            else:
                if q+mvn+fs>len(p):
                    raise SystemExit("truncated inter")
                mv=p[q:q+mvn]
                q+=mvn
                lattice=p[q:q+fs]
                q+=fs
                res=unblockize_residual(lattice,w,h,block)
                frame=motion_inverse(mv,res,prev,w,h,block,radius)
            out.extend(frame)
            prev=frame
        if q!=len(p):
            raise SystemExit("chunk trailing data")
    dst.write_bytes(out)


def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode")
    e.add_argument("src",type=Path); e.add_argument("dst",type=Path)
    e.add_argument("--width",type=int,required=True); e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,required=True); e.add_argument("--fps-den",type=int,required=True)
    e.add_argument("--gop",type=int,default=10); e.add_argument("--block",type=int,choices=(8,16),required=True)
    e.add_argument("--radius",type=int,choices=(2,4,6),default=4)
    d=sp.add_parser("decode")
    d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode":
        encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.block,a.radius)
    else:
        decode_file(a.src,a.dst)


if __name__=="__main__":
    main()
