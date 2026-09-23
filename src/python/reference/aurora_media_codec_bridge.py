#!/usr/bin/env python3
"""
AURORA Media codec bridge v0.1.

Connects the current proprietary AURORA/KHEPRI research codec paths to the
AURORA Media container without any external muxer/demuxer.

Audio packet:
  PCM s16le -> KMRL FULL256 TAIL16 -> KHEPRI EXP-37A -> packet payload

Video packet:
  raw YUV420p8 -> KSV-05 TEMP/MC8R4 routing -> KHEPRI EXP-37A -> packet payload

Each packet is independently decodable.
"""
from __future__ import annotations
from pathlib import Path
import shutil, tempfile

import kstream_kmrl_lab as lab
from ks06_plane_sparsity import enc_tail16, dec_tail16
import ksv09c_cached_motion_router as ksv09c

def _audio_front_encode(raw:Path,front:Path,channels:int,rate:int,block_ms:int=20):
    oe,od=lab.enc_fullplanes,lab.dec_fullplanes
    lab.enc_fullplanes,lab.dec_fullplanes=enc_tail16,dec_tail16
    try:
        lab.encode_file(raw,front,channels,rate,block_ms,2)
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=oe,od

def _audio_front_decode(front:Path,raw:Path):
    oe,od=lab.enc_fullplanes,lab.dec_fullplanes
    lab.enc_fullplanes,lab.dec_fullplanes=enc_tail16,dec_tail16
    try:
        lab.decode_file(front,raw)
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=oe,od

def _khepri_encode(exe:Path,src:Path,arc:Path):
    import subprocess
    subprocess.run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def _khepri_decode(exe:Path,arc:Path,outdir:Path)->Path:
    import subprocess
    if outdir.exists(): shutil.rmtree(outdir)
    subprocess.run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1: raise RuntimeError("unexpected KHEPRI decode output")
    return files[0]

def encode_audio_packet(raw_pcm:bytes,exe:Path,channels:int,rate:int)->bytes:
    with tempfile.TemporaryDirectory(prefix="aua1_") as td:
        t=Path(td); raw=t/"packet.pcm"; front=t/"packet.kmrl"; arc=t/"packet.aur"
        raw.write_bytes(raw_pcm)
        _audio_front_encode(raw,front,channels,rate)
        _khepri_encode(exe,front,arc)
        return arc.read_bytes()

def decode_audio_packet(payload:bytes,exe:Path)->bytes:
    with tempfile.TemporaryDirectory(prefix="aua1d_") as td:
        t=Path(td); arc=t/"packet.aur"; out=t/"kout"; raw=t/"packet.pcm"
        arc.write_bytes(payload)
        front=_khepri_decode(exe,arc,out)
        _audio_front_decode(front,raw)
        return raw.read_bytes()

def encode_video_packet(raw_yuv:bytes,exe:Path,w:int,h:int,fpsn:int,fpsd:int,
                        gop:int=10,route_span:int=20)->bytes:
    with tempfile.TemporaryDirectory(prefix="auv1_") as td:
        t=Path(td); raw=t/"packet.yuv"; arc=t/"packet.k5gr"
        raw.write_bytes(raw_yuv)
        ksv09c.encode_file(raw,arc,exe,w,h,fpsn,fpsd,gop,route_span)
        return arc.read_bytes()

def decode_video_packet(payload:bytes,exe:Path)->bytes:
    with tempfile.TemporaryDirectory(prefix="auv1d_") as td:
        t=Path(td); arc=t/"packet.k5gr"; raw=t/"packet.yuv"
        arc.write_bytes(payload)
        ksv09c.decode_router(arc,raw,exe)
        return raw.read_bytes()
