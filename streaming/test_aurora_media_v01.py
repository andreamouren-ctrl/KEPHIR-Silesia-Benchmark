#!/usr/bin/env python3
import hashlib, math, struct, tempfile
from pathlib import Path

from aurora_media_av_v01 import encode_av, decode_av, inspect
from aurora_media_container_v01 import AuroraDemuxer
from aurora_player_core_v01 import AuroraPlayerCore
from aurora_stream_protocol_v01 import StreamPacket, encode_packet, decode_packet, StreamReceiver

RATE=48000
CH=2
W=176
H=144
FPSN=25
FPSD=1

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_pcm(path:Path,seconds:float=1.0):
    n=int(RATE*seconds)
    out=bytearray()
    for i in range(n):
        a=int(12000*math.sin(2*math.pi*440*i/RATE))
        b=int(9000*math.sin(2*math.pi*660*i/RATE))
        out.extend(struct.pack("<hh",a,b))
    path.write_bytes(out)

def make_yuv(path:Path,frames:int=40):
    out=bytearray()
    cw=(W+1)//2; ch=(H+1)//2
    for f in range(frames):
        # Deterministic moving pattern; no external media decoder involved.
        for y in range(H):
            for x in range(W):
                out.append((x+y+f*3+((x+f)//16)*5)&255)
        for y in range(ch):
            for x in range(cw):
                out.append((96+x+f*2)&255)
        for y in range(ch):
            for x in range(cw):
                out.append((160+y+f)&255)
    path.write_bytes(out)

def expect_fail(fn):
    try: fn()
    except Exception: return True
    raise AssertionError("expected failure")

def main():
    import argparse, json
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    a=ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="aum_v01_") as td:
        t=Path(td)
        pcm=t/"in.pcm"; yuv=t/"in.yuv"; aum=t/"sample.aum"
        pcm2=t/"out.pcm"; yuv2=t/"out.yuv"
        make_pcm(pcm,1.0); make_yuv(yuv,40)

        src_audio_sha=sha(pcm); src_video_sha=sha(yuv)
        enc=encode_av(pcm,yuv,aum,a.kephir,RATE,CH,W,H,FPSN,FPSD,200,20,10)
        meta=inspect(aum)
        dec=decode_av(aum,pcm2,yuv2,a.kephir)
        assert sha(pcm2)==src_audio_sha
        assert sha(yuv2)==src_video_sha

        with AuroraDemuxer(aum) as d:
            assert len(d.tracks)==2
            assert len(d.index)>=4
            v=d.seek(2,700_000,True)
            assert v is not None and v.pts<=700_000
            e=d.index[0]
            good=d.read_packet(e)
            wire=encode_packet(StreamPacket(0,e.track_id,e.flags,e.pts,e.duration,good))
            p=decode_packet(wire)
            assert p.payload==good
            rx=StreamReceiver()
            assert rx.accept(wire).sequence==0
            bad=bytearray(wire); bad[-1]^=1
            assert expect_fail(lambda: decode_packet(bytes(bad)))

        player=AuroraPlayerCore(aum,a.kephir)
        try:
            ps=player.verify()
            seek_start=player.seek_pts(700_000)
            assert seek_start<=700_000
            assert ps["audio_packets"]>0 and ps["video_packets"]>0
        finally:
            player.close()

        # Corrupt a container payload byte: packet CRC must reject it.
        broken=t/"broken.aum"
        blob=bytearray(aum.read_bytes())
        with AuroraDemuxer(aum) as d:
            first=d.index[0]
            # payload begins immediately after fixed packet header (32 bytes).
            from aurora_media_container_v01 import PACKET_HDR
            pos=first.file_offset+PACKET_HDR.size
        blob[pos]^=1
        broken.write_bytes(blob)
        def read_broken():
            with AuroraDemuxer(broken) as d:
                d.read_packet(d.index[0])
        assert expect_fail(read_broken)

        result={
          "status":"PASS",
          "container_bytes":aum.stat().st_size,
          "source_audio_sha256":src_audio_sha,
          "decoded_audio_sha256":sha(pcm2),
          "source_video_sha256":src_video_sha,
          "decoded_video_sha256":sha(yuv2),
          "track_count":len(meta["tracks"]),
          "packet_count":meta["packet_count"],
          "player":ps,
          "seek_start_us":seek_start,
          "container_crc_rejection":True,
          "stream_crc_rejection":True,
          "native_mux_demux":True,
          "external_multimedia_dependency_in_core":False
        }
        Path("streaming/AURORA_MEDIA_V01_TEST_RESULTS.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))

if __name__=="__main__": main()
