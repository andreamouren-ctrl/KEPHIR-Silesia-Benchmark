#!/usr/bin/env python3
"""Emit deterministic Python KSV-20 H3 conformance vectors for native C++ tests."""
from pathlib import Path
import argparse
import json
import numpy as np

import ksv17_dense_integer_motion as k17
import ksv20_h3_refinement as k20

W=128
H=96


def make_previous():
    ys=W*H
    cs=(W//2)*(H//2)
    out=bytearray(ys+2*cs)

    for y in range(H):
        for x in range(W):
            out[y*W+x]=(
                x*13 + y*7 + ((x*y)%29)*3 + ((x//11)^(y//7))*17
            ) & 255

    cw=W//2
    ch=H//2
    for y in range(ch):
        for x in range(cw):
            i=y*cw+x
            out[ys+i]=(71 + x*5 + y*9 + ((x*y)%13)*7) & 255
            out[ys+cs+i]=(149 + x*11 + y*3 + ((x+y)%17)*5) & 255

    return bytes(out)


def make_current(previous: bytes):
    ys=W*H
    cs=(W//2)*(H//2)
    py=np.frombuffer(previous[:ys],dtype=np.uint8).reshape(H,W)
    pu=np.frombuffer(previous[ys:ys+cs],dtype=np.uint8).reshape(H//2,W//2)
    pv=np.frombuffer(previous[ys+cs:],dtype=np.uint8).reshape(H//2,W//2)

    cy=np.empty_like(py)
    for y in range(H):
        for x in range(W):
            if y < H//3:
                dx,dy=1,-1
            elif y < 2*H//3:
                dx,dy=-3,1
            else:
                dx,dy=3,3

            sx=x+dx
            sy=y+dy
            if 0<=sx<W and 0<=sy<H:
                cy[y,x]=py[sy,sx]
            else:
                cy[y,x]=(x*19+y*23+31)&255

    # Add a small independently moving textured patch.
    for y in range(32,56):
        for x in range(48,80):
            sx=min(W-1,max(0,x-1))
            sy=min(H-1,max(0,y+3))
            cy[y,x]=py[sy,sx]

    # Chroma intentionally does not assume one of the two rounding policies;
    # both reference residual variants must therefore be checked independently.
    cu=np.roll(pu,shift=(1,-1),axis=(0,1)).copy()
    cv=np.roll(pv,shift=(-1,2),axis=(0,1)).copy()
    cu[:1,:]=17
    cu[:,:1]=33
    cv[-1:,:]=201
    cv[:,-2:]=93

    return cy.tobytes()+cu.tobytes()+cv.tobytes()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)

    prev=make_previous()
    cur=make_current(prev)

    motion,residuals,stats=k20.h3_motion_residuals(cur,prev,W,H)
    floor=residuals[k17.CHROMA_FLOOR]
    trunc=residuals[k17.CHROMA_TRUNC]

    (args.out/"previous.yuv").write_bytes(prev)
    (args.out/"current.yuv").write_bytes(cur)
    (args.out/"motion.bin").write_bytes(motion)
    (args.out/"residual_floor.bin").write_bytes(floor)
    (args.out/"residual_trunc.bin").write_bytes(trunc)
    (args.out/"meta.json").write_text(json.dumps({
        "width":W,
        "height":H,
        "motion_bytes":len(motion),
        "frame_bytes":len(cur),
        "stats":stats,
    },indent=2))

    print(
        "KSV21_PYTHON_CONFORMANCE_VECTOR_PASS",
        "width",W,
        "height",H,
        "blocks",len(motion),
        "mean_evals",f'{stats["mean_candidate_evaluations"]:.6f}',
        "odd_fraction",f'{stats["odd_any_fraction"]:.6f}',
    )


if __name__=="__main__":
    main()
