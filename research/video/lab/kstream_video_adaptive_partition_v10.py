#!/usr/bin/env python3
"""
KSV-10 adaptive 16x16 / 8x8 motion partition experiment.

Per 16x16 luma macroblock, compare:
- one 16x16 motion vector
- four independent 8x8 motion vectors

Decision uses luma SAD plus a configurable split penalty.
This is lossless and deterministic. Variable block partitioning is background
codec engineering; the AURORA research question is how this partitioning
interacts with KHEPRI final compression.
"""
import argparse, struct, zlib
from pathlib import Path
import numpy as np

from kstream_video_baseline import frame_sizes, split_frame
from kstream_video_motion_control import spatial_frame, spatial_frame_inv, candidates, split_np

MAGIC=b"KSA1"
VERSION=1
FMT=1
HDR=struct.Struct("<4sBBBBHHII")  # magic,ver,fmt,radius,penalty_id,w,h,fpsn,fpsd
CHUNK=struct.Struct("<III")

def best_mv(cur,ref_plane,x0,y0,block,w,h,cand):
    best_i=None; best_cost=None
    for i,(dx,dy) in enumerate(cand):
        sx=x0+dx; sy=y0+dy
        if sx<0 or sy<0 or sx+block>w or sy+block>h: continue
        r=ref_plane[sy:sy+block,sx:sx+block].astype(np.int16)
        cost=int(np.abs(cur-r).sum())
        if best_cost is None or cost<best_cost:
            best_cost=cost; best_i=i
    if best_i is None: raise ValueError("no candidate")
    return best_i,best_cost

def motion_residual_adaptive(frame,prev,w,h,radius,split_penalty):
    cy,cu,cv=split_np(frame,w,h)
    py,pu,pv=split_np(prev,w,h)
    cand=candidates(radius)
    mbw=w//16; mbh=h//16
    modes=bytearray(mbw*mbh)
    vectors=bytearray()
    ry=np.empty_like(cy); ru=np.empty_like(cu); rv=np.empty_like(cv)

    mi=0
    for my in range(mbh):
        y0=my*16
        for mx in range(mbw):
            x0=mx*16
            cur16=cy[y0:y0+16,x0:x0+16].astype(np.int16)
            i16,c16=best_mv(cur16,py,x0,y0,16,w,h,cand)

            split_cost=0; split_info=[]
            for sy in (0,8):
                for sx in (0,8):
                    cur8=cy[y0+sy:y0+sy+8,x0+sx:x0+sx+8].astype(np.int16)
                    ii,cc=best_mv(cur8,py,x0+sx,y0+sy,8,w,h,cand)
                    split_cost+=cc; split_info.append((sx,sy,ii))

            split = (split_cost + split_penalty) < c16
            modes[mi]=1 if split else 0; mi+=1

            parts=split_info if split else [(0,0,i16)]
            pblock=8 if split else 16
            cblock=pblock//2
            for sx,sy,idx in parts:
                vectors.append(idx)
                dx,dy=cand[idx]
                lx=x0+sx; ly=y0+sy
                cur=cy[ly:ly+pblock,lx:lx+pblock].astype(np.int16)
                ref=py[ly+dy:ly+dy+pblock,lx+dx:lx+dx+pblock].astype(np.int16)
                ry[ly:ly+pblock,lx:lx+pblock]=((cur-ref)&255).astype(np.uint8)

                cx=lx//2; cy0=ly//2; cdx=dx//2; cdy=dy//2
                ucur=cu[cy0:cy0+cblock,cx:cx+cblock].astype(np.int16)
                uref=pu[cy0+cdy:cy0+cdy+cblock,cx+cdx:cx+cdx+cblock].astype(np.int16)
                vcur=cv[cy0:cy0+cblock,cx:cx+cblock].astype(np.int16)
                vref=pv[cy0+cdy:cy0+cdy+cblock,cx+cdx:cx+cdx+cblock].astype(np.int16)
                ru[cy0:cy0+cblock,cx:cx+cblock]=((ucur-uref)&255).astype(np.uint8)
                rv[cy0:cy0+cblock,cx:cx+cblock]=((vcur-vref)&255).astype(np.uint8)

    return bytes(modes),bytes(vectors),ry.tobytes()+ru.tobytes()+rv.tobytes()

def motion_inverse_adaptive(modes,vectors,res,prev,w,h,radius):
    py,pu,pv=split_np(prev,w,h)
    ys,cs,cw,ch=frame_sizes(w,h)
    ry=np.frombuffer(res[:ys],dtype=np.uint8).reshape(h,w)
    ru=np.frombuffer(res[ys:ys+cs],dtype=np.uint8).reshape(ch,cw)
    rv=np.frombuffer(res[ys+cs:],dtype=np.uint8).reshape(ch,cw)
    oy=np.empty_like(py); ou=np.empty_like(pu); ov=np.empty_like(pv)
    cand=candidates(radius)
    mbw=w//16; mbh=h//16
    if len(modes)!=mbw*mbh: raise ValueError("bad mode map")
    vi=0; mi=0
    for my in range(mbh):
        y0=my*16
        for mx in range(mbw):
            x0=mx*16
            split=bool(modes[mi]); mi+=1
            parts=[(0,0)] if not split else [(0,0),(8,0),(0,8),(8,8)]
            pblock=8 if split else 16
            cblock=pblock//2
            for sx,sy in parts:
                if vi>=len(vectors): raise ValueError("truncated vectors")
                idx=vectors[vi]; vi+=1
                if idx>=len(cand): raise ValueError("bad vector")
                dx,dy=cand[idx]
                lx=x0+sx; ly=y0+sy
                ref=py[ly+dy:ly+dy+pblock,lx+dx:lx+dx+pblock].astype(np.int16)
                rr=ry[ly:ly+pblock,lx:lx+pblock].astype(np.int16)
                oy[ly:ly+pblock,lx:lx+pblock]=((ref+rr)&255).astype(np.uint8)

                cx=lx//2; cy0=ly//2; cdx=dx//2; cdy=dy//2
                uref=pu[cy0+cdy:cy0+cdy+cblock,cx+cdx:cx+cdx+cblock].astype(np.int16)
                vref=pv[cy0+cdy:cy0+cdy+cblock,cx+cdx:cx+cdx+cblock].astype(np.int16)
                urr=ru[cy0:cy0+cblock,cx:cx+cblock].astype(np.int16)
                vrr=rv[cy0:cy0+cblock,cx:cx+cblock].astype(np.int16)
                ou[cy0:cy0+cblock,cx:cx+cblock]=((uref+urr)&255).astype(np.uint8)
                ov[cy0:cy0+cblock,cx:cx+cblock]=((vref+vrr)&255).astype(np.uint8)
    if vi!=len(vectors): raise ValueError("extra vectors")
    return oy.tobytes()+ou.tobytes()+ov.tobytes()

def encode_file(src:Path,dst:Path,w:int,h:int,fpsn:int,fpsd:int,gop:int,radius:int,split_penalty:int):
    if w%16 or h%16: raise ValueError("dimensions must be divisible by 16")
    raw=src.read_bytes(); ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs
    if len(raw)%fs: raise ValueError("incomplete frames")
    total=len(raw)//fs; mbn=(w//16)*(h//16)
    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC,VERSION,FMT,radius,min(split_penalty//256,255),w,h,fpsn,fpsd))
        off=0
        while off<total:
            n=min(gop,total-off); payload=bytearray(); prev=None
            for j in range(n):
                frame=raw[(off+j)*fs:(off+j+1)*fs]
                if prev is None:
                    payload.extend(spatial_frame(frame,w,h))
                else:
                    modes,vec,res=motion_residual_adaptive(frame,prev,w,h,radius,split_penalty)
                    payload.extend(modes)
                    payload.extend(struct.pack("<I",len(vec)))
                    payload.extend(vec); payload.extend(res)
                prev=frame
            p=bytes(payload); f.write(CHUNK.pack(n,len(p),zlib.crc32(p)&0xffffffff)); f.write(p)
            off+=n

def decode_file(src:Path,dst:Path,gop:int):
    b=src.read_bytes()
    magic,ver,fmt,radius,penalty_id,w,h,fpsn,fpsd=HDR.unpack_from(b,0)
    if magic!=MAGIC or ver!=VERSION or fmt!=FMT: raise ValueError("bad stream")
    ys,cs,_,_=frame_sizes(w,h); fs=ys+2*cs; mbn=(w//16)*(h//16)
    pos=HDR.size; out=bytearray()
    while pos<len(b):
        n,sz,crc=CHUNK.unpack_from(b,pos); pos+=CHUNK.size
        p=b[pos:pos+sz]; pos+=sz
        if zlib.crc32(p)&0xffffffff!=crc: raise ValueError("crc")
        q=0; prev=None
        for _ in range(n):
            if prev is None:
                frame=spatial_frame_inv(p[q:q+fs],w,h); q+=fs
            else:
                modes=p[q:q+mbn]; q+=mbn
                vlen=struct.unpack_from("<I",p,q)[0]; q+=4
                vec=p[q:q+vlen]; q+=vlen
                res=p[q:q+fs]; q+=fs
                frame=motion_inverse_adaptive(modes,vec,res,prev,w,h,radius)
            out.extend(frame); prev=frame
        if q!=len(p): raise ValueError("trailing")
    dst.write_bytes(out)

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode"); e.add_argument("src",type=Path); e.add_argument("dst",type=Path)
    e.add_argument("--width",type=int,required=True); e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,required=True); e.add_argument("--fps-den",type=int,required=True)
    e.add_argument("--gop",type=int,default=10); e.add_argument("--radius",type=int,default=4)
    e.add_argument("--split-penalty",type=int,required=True)
    d=sp.add_parser("decode"); d.add_argument("src",type=Path); d.add_argument("dst",type=Path)
    d.add_argument("--gop",type=int,default=10)
    a=ap.parse_args()
    if a.cmd=="encode": encode_file(a.src,a.dst,a.width,a.height,a.fps_num,a.fps_den,a.gop,a.radius,a.split_penalty)
    else: decode_file(a.src,a.dst,a.gop)
if __name__=="__main__":main()
