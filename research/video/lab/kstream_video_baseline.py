#!/usr/bin/env python3
"""
KHEPRI Stream video baseline (KS-V01).

Reversible YUV420p 8-bit transforms only.
All predictors here are BACKGROUND controls, not candidate IP.
"""
import argparse
import struct
import zlib
from pathlib import Path

MAGIC=b"KSV1"
VERSION=1
HDR=struct.Struct("<4sBBBBHHII")  # magic,ver,mode,format,gop,w,h,fps_num,fps_den
CHUNK=struct.Struct("<III")        # frames,payload_size,crc
FMT_YUV420P8=1


def paeth(a,b,c):
    p=a+b-c
    pa=abs(p-a); pb=abs(p-b); pc=abs(p-c)
    if pa<=pb and pa<=pc: return a
    if pb<=pc: return b
    return c


def plane_spatial(src,w,h,mode):
    out=bytearray(len(src))
    for y in range(h):
        row=y*w
        for x in range(w):
            i=row+x
            left=src[i-1] if x else 0
            up=src[i-w] if y else 0
            ul=src[i-w-1] if x and y else 0
            if mode==1: pred=left
            elif mode==2: pred=paeth(left,up,ul)
            else: raise ValueError("bad spatial mode")
            out[i]=(src[i]-pred)&255
    return bytes(out)


def plane_spatial_inv(res,w,h,mode):
    out=bytearray(len(res))
    for y in range(h):
        row=y*w
        for x in range(w):
            i=row+x
            left=out[i-1] if x else 0
            up=out[i-w] if y else 0
            ul=out[i-w-1] if x and y else 0
            if mode==1: pred=left
            elif mode==2: pred=paeth(left,up,ul)
            else: raise ValueError("bad spatial mode")
            out[i]=(pred+res[i])&255
    return bytes(out)


def frame_sizes(w,h):
    y=w*h
    cw=(w+1)//2; ch=(h+1)//2
    c=cw*ch
    return y,c,cw,ch


def split_frame(frame,w,h):
    ys,cs,cw,ch=frame_sizes(w,h)
    if len(frame)!=ys+2*cs: raise ValueError("bad frame size")
    return frame[:ys],frame[ys:ys+cs],frame[ys+cs:],cw,ch


def join_frame(y,u,v):
    return y+u+v


def transform_frame(frame,w,h,mode,prev=None):
    y,u,v,cw,ch=split_frame(frame,w,h)
    if mode in (1,2):
        return join_frame(plane_spatial(y,w,h,mode),
                          plane_spatial(u,cw,ch,mode),
                          plane_spatial(v,cw,ch,mode))
    if mode==3:
        if prev is None:
            return join_frame(plane_spatial(y,w,h,2),
                              plane_spatial(u,cw,ch,2),
                              plane_spatial(v,cw,ch,2))
        return bytes((a-b)&255 for a,b in zip(frame,prev))
    raise ValueError("bad mode")


def inverse_frame(res,w,h,mode,prev=None):
    y,u,v,cw,ch=split_frame(res,w,h)
    if mode in (1,2):
        return join_frame(plane_spatial_inv(y,w,h,mode),
                          plane_spatial_inv(u,cw,ch,mode),
                          plane_spatial_inv(v,cw,ch,mode))
    if mode==3:
        if prev is None:
            return join_frame(plane_spatial_inv(y,w,h,2),
                              plane_spatial_inv(u,cw,ch,2),
                              plane_spatial_inv(v,cw,ch,2))
        return bytes((a+b)&255 for a,b in zip(res,prev))
    raise ValueError("bad mode")


def encode_file(src:Path,dst:Path,w:int,h:int,fps_num:int,fps_den:int,gop:int,mode:int):
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h)
    fs=ys+2*cs
    if len(raw)%fs: raise SystemExit("input is not complete yuv420p frames")
    total=len(raw)//fs

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,mode,FMT_YUV420P8,gop,w,h,fps_num,fps_den))
        off=0
        while off<total:
            n=min(gop,total-off)
            payload=bytearray()
            prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                payload.extend(transform_frame(frame,w,h,mode,prev))
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff))
            f.write(p)
            off+=n


def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size: raise SystemExit("truncated header")
    magic,ver,mode,fmt,gop,w,h,fpsn,fpsd=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT_YUV420P8 or mode not in (1,2,3):
        raise SystemExit("unsupported stream")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    pos=HDR.size; out=bytearray()
    while pos<len(data):
        if pos+CHUNK.size>len(data): raise SystemExit("truncated chunk")
        n,sz,crc=CHUNK.unpack_from(data,pos); pos+=CHUNK.size
        if n<1 or n>gop or sz!=n*fs or pos+sz>len(data): raise SystemExit("bad chunk")
        p=data[pos:pos+sz];pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise SystemExit("crc")
        prev=None
        for j in range(n):
            res=p[j*fs:(j+1)*fs]
            frame=inverse_frame(res,w,h,mode,prev)
            out.extend(frame);prev=frame
    dst.write_bytes(out)


def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode");e.add_argument("src",type=Path);e.add_argument("dst",type=Path)
    e.add_argument("--width",type=int,required=True);e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,default=30000);e.add_argument("--fps-den",type=int,default=1001)
    e.add_argument("--gop",type=int,default=10);e.add_argument("--mode",type=int,choices=(1,2,3),required=True)
    d=sp.add_parser("decode");d.add_argument("src",type=Path);d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.mode)
    else: decode_file(a.src,a.dst)


if __name__=="__main__":
    main()
