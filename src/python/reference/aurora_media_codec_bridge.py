#!/usr/bin/env python3
"""
AURORA Media codec bridge v0.1.

Connects the current proprietary AURORA/KHEPRI research codec paths to the
AURORA Media container without any external muxer/demuxer.

Audio packet:
  signed PCM 16-bit LE -> canonical KMRL FULL256 + TAIL16
  signed PCM 24/32-bit LE -> generalized KMRL v2 adaptive residual geometry
  -> KHEPRI EXP-37A -> packet payload

Video packet:
  raw YUV420p8 -> KSV-05 TEMP/MC8R4 routing -> KHEPRI EXP-37A -> packet payload

Each packet is independently decodable.
"""
from __future__ import annotations
from pathlib import Path
import shutil, tempfile

import kstream_kmrl_frontend as kmrl
import kstream_kmrl_lab as kmrl_lab
import ksv09c_cached_motion_router as ksv09c

def _audio_front_encode(raw:Path,front:Path,channels:int,rate:int,
                        bits:int=16,block_ms:int=20):
    """Encode one independently recoverable AURORA audio packet.

    Canonical s16 path:
      reversible stereo decorrelation -> KMRL carry prediction
      -> FULL256 planes -> TAIL16 -> KHEPRI.

    Higher-resolution PCM keeps the generalized KMRL v2 path until its
    FULL256/TAIL16 geometry receives separate validation.
    """
    if bits == 16:
        kmrl_lab.encode_file(raw,front,channels,rate,block_ms,4)
    else:
        kmrl.encode_file(raw,front,channels,rate,bits,block_ms,"adaptive")

def _audio_front_decode(front:Path,raw:Path):
    magic=front.read_bytes()[:4]
    if magic == kmrl_lab.MAGIC:
        kmrl_lab.decode_file(front,raw)
    elif magic == kmrl.MAGIC:
        kmrl.decode_file(front,raw)
    else:
        raise RuntimeError("unknown AURORA audio frontend magic")

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

def encode_audio_packet(raw_pcm:bytes,exe:Path,channels:int,rate:int,bits:int=16)->bytes:
    if bits not in (16,24,32):
        raise ValueError("AURORA audio supports signed PCM 16/24/32-bit")
    if channels < 1 or channels > 32:
        raise ValueError("AURORA audio channel count must be 1..32")
    if rate < 8_000 or rate > 384_000:
        raise ValueError("AURORA audio sample rate must be 8000..384000 Hz")
    frame_bytes=channels*(bits//8)
    if len(raw_pcm)%frame_bytes:
        raise ValueError("AURORA audio PCM payload is not frame-aligned")
    with tempfile.TemporaryDirectory(prefix="aua2_") as td:
        t=Path(td); raw=t/"packet.pcm"; front=t/"packet.kmrl"; arc=t/"packet.aur"
        raw.write_bytes(raw_pcm)
        _audio_front_encode(raw,front,channels,rate,bits)
        _khepri_encode(exe,front,arc)
        return arc.read_bytes()

def decode_audio_packet(payload:bytes,exe:Path)->bytes:
    with tempfile.TemporaryDirectory(prefix="aua2d_") as td:
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
