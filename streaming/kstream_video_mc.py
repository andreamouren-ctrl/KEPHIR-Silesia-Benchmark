#!/usr/bin/env python3
"""
KSV-MC control frontend.

Reversible integer-pixel block motion compensation for research baselines.
BACKGROUND technique only; no candidate-IP claim is made.
"""
import argparse
import struct
import zlib
from pathlib import Path
import numpy as np

from kstream_video_baseline import plane_spatial, plane_spatial_inv, frame_sizes, split_frame, join_frame

MAGIC=b"KSM1"
VERSION=1
FMT_YUV420P8=1
HDR=struct.Struct("<4sBBBBBHHII")  # magic,ver,fmt,gop,block,radius,w,h,fpsn,fpsd
CHUNK=struct.Struct("<III")

def candidates(radius):
    vals=range(-radius,radius+1,2)
    c=[(dx,dy) for dy in vals for dx in vals]
    c.sort(key=lambda p:(abs(p[0])+abs(p[1]),abs(p[1]),abs(p[0]),p[1],p[0]))
    return c

def split_np(frame,w,h):
    y,u,v,cw,ch=split_frame(frame,w,h)
    return (np.frombuffer(y,dtype=np.uint8).reshape(h,w),
            np.frombuffer(u,dtype=np.uint8).reshape(ch,cw),
            np.frombuffer(v,dtype=np.uint8).reshape(ch,cw))

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

def motion_residual(frame,prev,w,h,block,radius):
    cy,cu,cv=split_np(frame,w,h)
    py,pu,pv=split_np(prev,w,h)
    cand=candidates(radius)
    bh=h//block; bw=w//block
    mv=bytearray(bh*bw)
    ry=np.empty_like(cy)
    ru=np.empty_like(cu)
    rv=np.empty_like(cv)
    cb=block//2

    k=0
    for by in range(bh):
        y0=by*block
        for bx in range(bw):
            x0=bx*block
            cur=cy[y0:y0+block,x0:x0+block].astype(np.int16)
            best_i=None; best_cost=None
            for i,(dx,dy) in enumerate(cand):
                sx=x0+dx; sy=y0+dy
                if sx<0 or sy<0 or sx+block>w or sy+block>h:
                    continue
                ref=py[sy:sy+block,sx:sx+block].astype(np.int16)
                cost=int(np.abs(cur-ref).sum())
                if best_cost is None or cost<best_cost:
                    best_cost=cost; best_i=i
            if best_i is None:
                raise ValueError("no motion candidate")
            mv[k]=best_i; k+=1
            dx,dy=cand[best_i]
            ref=py[y0+dy:y0+dy+block,x0+dx:x0+dx+block].astype(np.int16)
            ry[y0:y0+block,x0:x0+block]=((cur-ref)&255).astype(np.uint8)

            cx0=x0//2; cy0=y0//2; cdx=dx//2; cdy=dy//2
            ucur=cu[cy0:cy0+cb,cx0:cx0+cb].astype(np.int16)
            uref=pu[cy0+cdy:cy0+cdy+cb,cx0+cdx:cx0+cdx+cb].astype(np.int16)
            vcur=cv[cy0:cy0+cb,cx0:cx0+cb].astype(np.int16)
            vref=pv[cy0+cdy:cy0+cdy+cb,cx0+cdx:cx0+cdx+cb].astype(np.int16)
            ru[cy0:cy0+cb,cx0:cx0+cb]=((ucur-uref)&255).astype(np.uint8)
            rv[cy0:cy0+cb,cx0:cx0+cb]=((vcur-vref)&255).astype(np.uint8)

    return bytes(mv), ry.tobytes()+ru.tobytes()+rv.tobytes()

def motion_inverse(mv,res,prev,w,h,block,radius):
    py,pu,pv=split_np(prev,w,h)
    ys,cs,cw,ch=frame_sizes(w,h)
    ry=np.frombuffer(res[:ys],dtype=np.uint8).reshape(h,w)
    ru=np.frombuffer(res[ys:ys+cs],dtype=np.uint8).reshape(ch,cw)
    rv=np.frombuffer(res[ys+cs:],dtype=np.uint8).reshape(ch,cw)
    oy=np.empty_like(py); ou=np.empty_like(pu); ov=np.empty_like(pv)
    cand=candidates(radius)
    bh=h//block; bw=w//block; cb=block//2
    if len(mv)!=bh*bw: raise ValueError("bad motion map")
    k=0
    for by in range(bh):
        y0=by*block
        for bx in range(bw):
            x0=bx*block
            idx=mv[k]; k+=1
            if idx>=len(cand): raise ValueError("bad motion index")
            dx,dy=cand[idx]
            sx=x0+dx; sy=y0+dy
            if sx<0 or sy<0 or sx+block>w or sy+block>h:
                raise ValueError("motion vector out of bounds")
            ref=py[sy:sy+block,sx:sx+block].astype(np.int16)
            rr=ry[y0:y0+block,x0:x0+block].astype(np.int16)
            oy[y0:y0+block,x0:x0+block]=((ref+rr)&255).astype(np.uint8)

            cx0=x0//2; cy0=y0//2; cdx=dx//2; cdy=dy//2
            uref=pu[cy0+cdy:cy0+cdy+cb,cx0+cdx:cx0+cdx+cb].astype(np.int16)
            vref=pv[cy0+cdy:cy0+cdy+cb,cx0+cdx:cx0+cdx+cb].astype(np.int16)
            urr=ru[cy0:cy0+cb,cx0:cx0+cb].astype(np.int16)
            vrr=rv[cy0:cy0+cb,cx0:cx0+cb].astype(np.int16)
            ou[cy0:cy0+cb,cx0:cx0+cb]=((uref+urr)&255).astype(np.uint8)
            ov[cy0:cy0+cb,cx0:cx0+cb]=((vref+vrr)&255).astype(np.uint8)
    return oy.tobytes()+ou.tobytes()+ov.tobytes()

def encode_file(src:Path,dst:Path,w:int,h:int,fpsn:int,fpsd:int,gop:int,block:int,radius:int):
    if block not in (8,16) or radius not in (2,4,6) or radius%2:
        raise ValueError("unsupported control geometry")
    if w%block or h%block:
        raise ValueError("frame not divisible by block")
    raw=src.read_bytes()
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    if len(raw)%fs: raise SystemExit("input is not complete yuv420p frames")
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
                    payload.extend(spatial_frame(frame,w,h))
                else:
                    mv,res=motion_residual(frame,prev,w,h,block,radius)
                    if len(mv)!=mvn or len(res)!=fs: raise ValueError("internal size")
                    payload.extend(mv); payload.extend(res)
                prev=frame
            p=bytes(payload)
            f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n

def decode_file(src:Path,dst:Path):
    data=src.read_bytes()
    if len(data)<HDR.size: raise SystemExit("truncated header")
    magic,ver,fmt,gop,block,radius,w,h,fpsn,fpsd=HDR.unpack_from(data,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT_YUV420P8:
        raise SystemExit("unsupported stream")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    mvn=(w//block)*(h//block)
    pos=HDR.size; out=bytearray()
    while pos<len(data):
        if pos+CHUNK.size>len(data): raise SystemExit("truncated chunk header")
        n,sz,crc=CHUNK.unpack_from(data,pos); pos+=CHUNK.size
        if n<1 or n>gop or pos+sz>len(data): raise SystemExit("bad chunk")
        p=data[pos:pos+sz];pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise SystemExit("crc")
        q=0; prev=None
        for j in range(n):
            if prev is None:
                if q+fs>len(p): raise SystemExit("truncated intra")
                frame=spatial_frame_inv(p[q:q+fs],w,h); q+=fs
            else:
                if q+mvn+fs>len(p): raise SystemExit("truncated inter")
                mv=p[q:q+mvn]; q+=mvn
                res=p[q:q+fs]; q+=fs
                frame=motion_inverse(mv,res,prev,w,h,block,radius)
            out.extend(frame); prev=frame
        if q!=len(p): raise SystemExit("chunk trailing data")
    dst.write_bytes(out)

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode"); e.add_argument("src",type=Path); e.add_argument("dst",type=Path)
    e.add_argument("--width",type=int,required=True); e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,required=True); e.add_argument("--fps-den",type=int,required=True)
    e.add_argument("--gop",type=int,default=10); e.add_argument("--block",type=int,choices=(8,16),required=True)
    e.add_argument("--radius",type=int,choices=(2,4,6),default=4)
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.block,a.radius)
    else: decode_file(a.src,a.dst)
if __name__=="__main__": main()
