#!/usr/bin/env python3
"""
AURORA Audio Format Matrix.

This is a correctness/capability gate, not a compression-quality benchmark.
It exercises:
PCM -> AURORA audio frontend -> KHEPRI -> AUM -> demux -> decode -> byte-exact PCM.

Cases cover mono/stereo/multichannel, 16/24/32-bit integer PCM and common
high-resolution sample rates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import time
from pathlib import Path

from aurora_media_codec_bridge import encode_audio_packet, decode_audio_packet
from aurora_media_container import (
    AuroraMuxer,
    AuroraDemuxer,
    Track,
    TRACK_AUDIO,
    CODEC_AURORA_AUDIO,
    PKT_RECOVERY,
)

OUT=Path("results/audio/format_matrix")
TIMESCALE=1_000_000

CASES=[
    ("mono_s16_44100",1,44_100,16),
    ("stereo_s16_48000",2,48_000,16),
    ("surround_5_1_s16_48000",6,48_000,16),
    ("stereo_s24_96000",2,96_000,24),
    ("surround_5_1_s24_96000",6,96_000,24),
    ("stereo_s32_192000",2,192_000,32),
    ("surround_7_1_s32_96000",8,96_000,32),
]

def sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def clamp(v,lo,hi):
    return lo if v<lo else hi if v>hi else v

def pack_sample(v:int,bits:int)->bytes:
    if bits==16:
        return struct.pack("<h",v)
    if bits==24:
        u=v & 0xFFFFFF
        return bytes((u&255,(u>>8)&255,(u>>16)&255))
    if bits==32:
        return struct.pack("<i",v)
    raise ValueError(bits)

def make_pcm(channels:int,rate:int,bits:int,duration_s:float=0.20)->bytes:
    frames=max(1024,int(rate*duration_s))
    peak=(1<<(bits-1))-1
    scale=max(1,peak//8)
    out=bytearray()

    # Deterministic structured signal with per-channel frequency/phase,
    # slow trend and sparse transients. It is intentionally synthetic:
    # this gate tests exact format support, not codec superiority.
    for i in range(frames):
        t=i/rate
        transient = (i % max(257,rate//37)) == 0
        for ch in range(channels):
            f=173.0 + 61.0*ch
            g=37.0 + 11.0*(ch%3)
            phase=0.31*ch
            x=(
                0.52*math.sin(2.0*math.pi*f*t+phase)
                +0.19*math.sin(2.0*math.pi*g*t)
                +0.04*((i%211)-105)/105.0
            )
            if transient:
                x += 0.12 if (ch&1)==0 else -0.12
            v=clamp(int(round(x*scale)),-peak-1,peak)
            out.extend(pack_sample(v,bits))
    return bytes(out)

def run_case(name,channels,rate,bits,exe:Path):
    raw=make_pcm(channels,rate,bits)
    frames=len(raw)//(channels*(bits//8))

    t0=time.perf_counter()
    payload=encode_audio_packet(raw,exe,channels,rate,bits)
    encode_s=time.perf_counter()-t0

    case_dir=OUT/name
    case_dir.mkdir(parents=True,exist_ok=True)
    aum=case_dir/f"{name}.aum"

    duration_ticks=frames*TIMESCALE//rate
    with AuroraMuxer(
        aum,
        [Track(
            1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,
            rate,channels,bits,frames
        )],
        TIMESCALE,
    ) as mux:
        mux.write_packet(1,0,duration_ticks,payload,PKT_RECOVERY)

    with AuroraDemuxer(aum) as demux:
        track=demux.tracks[1]
        if (track.p1,track.p2,track.p3,track.p4)!=(rate,channels,bits,frames):
            raise RuntimeError(f"{name}: AUM audio metadata mismatch")
        entries=list(demux.packets(1))
        if len(entries)!=1:
            raise RuntimeError(f"{name}: unexpected packet count")
        packet_info,stored_payload=entries[0]
        if not (packet_info.flags & PKT_RECOVERY):
            raise RuntimeError(f"{name}: recovery flag missing")
        if stored_payload!=payload:
            raise RuntimeError(f"{name}: AUM payload mismatch")

    t0=time.perf_counter()
    decoded=decode_audio_packet(payload,exe)
    decode_s=time.perf_counter()-t0

    if decoded!=raw:
        raise RuntimeError(f"{name}: byte-exact PCM roundtrip failed")

    return {
        "name":name,
        "channels":channels,
        "sample_rate":rate,
        "bits_per_sample":bits,
        "frames":frames,
        "raw_bytes":len(raw),
        "payload_bytes":len(payload),
        "aum_bytes":aum.stat().st_size,
        "payload_percent_raw":100.0*len(payload)/len(raw),
        "encode_seconds":encode_s,
        "decode_seconds":decode_s,
        "sha256":sha256(raw),
        "bit_exact":True,
        "aum_metadata_ok":True,
        "recovery_flag_ok":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    args=ap.parse_args()

    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in CASES:
        row=run_case(*case,args.kephir)
        rows.append(row)
        print(
            "FORMAT_PASS",
            row["name"],
            f"ch={row['channels']}",
            f"rate={row['sample_rate']}",
            f"bits={row['bits_per_sample']}",
            f"raw={row['raw_bytes']}",
            f"payload={row['payload_bytes']}",
            f"ratio={row['payload_percent_raw']:.3f}",
            f"enc_s={row['encode_seconds']:.6f}",
            f"dec_s={row['decode_seconds']:.6f}",
        )

    result={
        "experiment":"AURORA Audio Format Matrix",
        "scope":"correctness/capability; synthetic signal; not a competitive compression benchmark",
        "cases":rows,
        "case_count":len(rows),
        "all_bit_exact":all(r["bit_exact"] for r in rows),
        "all_aum_metadata_ok":all(r["aum_metadata_ok"] for r in rows),
    }
    (OUT/"AUDIO_FORMAT_MATRIX.json").write_text(json.dumps(result,indent=2))
    print("AURORA_AUDIO_FORMAT_MATRIX_PASS",len(rows))

if __name__=="__main__":
    main()
