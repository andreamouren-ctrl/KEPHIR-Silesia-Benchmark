#!/usr/bin/env python3
"""
AURORA Media A/V tool v0.1.

First self-contained testable AURORA Media pipeline:
- owns the container, muxing, demuxing, indexing, timestamps, CRC and seek
- uses AURORA/KHEPRI audio/video payloads
- external multimedia frameworks are not required to read/write .aum

Input/output for v0.1 are raw PCM s16le and raw YUV420p8.
"""
from __future__ import annotations
import argparse, hashlib, heapq
from pathlib import Path

from aurora_media_container import (
    AuroraMuxer,AuroraDemuxer,Track,
    TRACK_AUDIO,TRACK_VIDEO,CODEC_AURORA_AUDIO,CODEC_AURORA_VIDEO,
    PKT_KEY,PKT_RECOVERY
)
from aurora_media_codec_bridge import (
    encode_audio_packet,decode_audio_packet,
    encode_video_packet,decode_video_packet
)

TIMESCALE=1_000_000

def sha(b:bytes): return hashlib.sha256(b).hexdigest()

def aframe_bytes(channels:int,bits:int=16):
    return channels*(bits//8)

def vframe_bytes(w:int,h:int):
    return w*h + 2*((w+1)//2)*((h+1)//2)

def us_from_audio_sample(sample:int,rate:int):
    return (sample*TIMESCALE)//rate

def us_from_video_frame(frame:int,fpsn:int,fpsd:int):
    return (frame*TIMESCALE*fpsd)//fpsn

def encode_av(audio:Path,video:Path,out:Path,kephir:Path,
              rate:int,channels:int,w:int,h:int,fpsn:int,fpsd:int,
              audio_packet_ms:int=200,video_packet_frames:int=20,gop:int=10):
    apcm=audio.read_bytes()
    vyuv=video.read_bytes()
    afb=aframe_bytes(channels)
    vfb=vframe_bytes(w,h)
    if len(apcm)%afb: raise ValueError("bad PCM size")
    if len(vyuv)%vfb: raise ValueError("bad YUV size")
    samples=len(apcm)//afb
    frames=len(vyuv)//vfb
    aps=max(1,rate*audio_packet_ms//1000)

    tracks=[
      Track(1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,rate,channels,16,aps),
      Track(2,TRACK_VIDEO,CODEC_AURORA_VIDEO,0,w,h,fpsn,fpsd),
    ]

    packets=[]
    for s0 in range(0,samples,aps):
        n=min(aps,samples-s0)
        raw=apcm[s0*afb:(s0+n)*afb]
        payload=encode_audio_packet(raw,kephir,channels,rate)
        pts=us_from_audio_sample(s0,rate)
        dur=us_from_audio_sample(n,rate)
        packets.append((pts,1,dur,payload,PKT_RECOVERY))

    for f0 in range(0,frames,video_packet_frames):
        n=min(video_packet_frames,frames-f0)
        raw=vyuv[f0*vfb:(f0+n)*vfb]
        payload=encode_video_packet(raw,kephir,w,h,fpsn,fpsd,gop,video_packet_frames)
        pts=us_from_video_frame(f0,fpsn,fpsd)
        dur=us_from_video_frame(n,fpsn,fpsd)
        packets.append((pts,2,dur,payload,PKT_KEY|PKT_RECOVERY))

    packets.sort(key=lambda x:(x[0],x[1]))
    with AuroraMuxer(out,tracks,TIMESCALE) as mux:
        for pts,tid,dur,payload,flags in packets:
            mux.write_packet(tid,pts,dur,payload,flags)

    return dict(audio_samples=samples,video_frames=frames,packets=len(packets),
                audio_sha256=sha(apcm),video_sha256=sha(vyuv),
                container_bytes=out.stat().st_size)

def decode_av(src:Path,audio_out:Path,video_out:Path,kephir:Path):
    ao=bytearray(); vo=bytearray()
    with AuroraDemuxer(src) as demux:
        for e,payload in demux.packets():
            if e.track_id==1: ao.extend(decode_audio_packet(payload,kephir))
            elif e.track_id==2: vo.extend(decode_video_packet(payload,kephir))
    audio_out.write_bytes(ao); video_out.write_bytes(vo)
    return dict(audio_bytes=len(ao),video_bytes=len(vo),
                audio_sha256=sha(bytes(ao)),video_sha256=sha(bytes(vo)))

def inspect(src:Path):
    with AuroraDemuxer(src) as d:
        return {
          "timescale":d.timescale,
          "tracks":[vars(t) for t in d.tracks.values()],
          "packet_count":len(d.index),
          "packets":[vars(e) for e in d.index]
        }

def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="cmd",required=True)
    e=sp.add_parser("encode")
    e.add_argument("--audio",type=Path,required=True); e.add_argument("--video",type=Path,required=True)
    e.add_argument("--out",type=Path,required=True); e.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    e.add_argument("--rate",type=int,default=48000); e.add_argument("--channels",type=int,default=2)
    e.add_argument("--width",type=int,required=True); e.add_argument("--height",type=int,required=True)
    e.add_argument("--fps-num",type=int,required=True); e.add_argument("--fps-den",type=int,required=True)
    e.add_argument("--audio-packet-ms",type=int,default=200); e.add_argument("--video-packet-frames",type=int,default=20)
    d=sp.add_parser("decode")
    d.add_argument("--input",type=Path,required=True); d.add_argument("--audio-out",type=Path,required=True)
    d.add_argument("--video-out",type=Path,required=True); d.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    i=sp.add_parser("inspect"); i.add_argument("input",type=Path)
    a=ap.parse_args()
    if a.cmd=="encode":
        print(encode_av(a.audio,a.video,a.out,a.kephir,a.rate,a.channels,a.width,a.height,a.fps_num,a.fps_den,a.audio_packet_ms,a.video_packet_frames))
    elif a.cmd=="decode":
        print(decode_av(a.input,a.audio_out,a.video_out,a.kephir))
    else:
        import json; print(json.dumps(inspect(a.input),indent=2))

if __name__=="__main__": main()
