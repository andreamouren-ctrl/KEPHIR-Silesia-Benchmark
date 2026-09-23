#!/usr/bin/env python3
"""
AURORA Player Core v0.1

Own demux/decode/sync/seek path for .aum.
No FFmpeg or third-party demuxer/player is required.

The v0.1 player is intentionally headless: decoded audio/video are delivered
to callbacks. A GUI/audio-device front-end can sit on top without changing the
container or codec core.
"""
from __future__ import annotations
from pathlib import Path
from aurora_media_container import AuroraDemuxer,PKT_KEY,PKT_RECOVERY
from aurora_media_codec_bridge import decode_audio_packet,decode_video_packet

class AuroraPlayerCore:
    def __init__(self,path:Path,kephir:Path):
        self.path=Path(path)
        self.kephir=Path(kephir)
        self.demux=AuroraDemuxer(self.path)

    def close(self): self.demux.close()

    def timeline(self,start_pts:int=0):
        entries=[e for e in self.demux.index if e.pts>=start_pts]
        entries.sort(key=lambda e:(e.pts,e.track_id))
        for e in entries:
            yield e

    def seek_pts(self,pts:int):
        # Seek to nearest video recovery point at/before requested time.
        v=self.demux.seek(2,pts,True)
        a=self.demux.seek(1,v.pts if v else pts,True)
        starts=[x.pts for x in (a,v) if x is not None]
        return min(starts) if starts else 0

    def play(self,start_pts:int=0,audio_sink=None,video_sink=None):
        stats={"audio_packets":0,"video_packets":0,"start_pts":start_pts}
        for e in self.timeline(start_pts):
            payload=self.demux.read_packet(e)
            if e.track_id==1:
                pcm=decode_audio_packet(payload,self.kephir)
                stats["audio_packets"]+=1
                if audio_sink: audio_sink(e.pts,e.duration,pcm)
            elif e.track_id==2:
                yuv=decode_video_packet(payload,self.kephir)
                stats["video_packets"]+=1
                if video_sink: video_sink(e.pts,e.duration,yuv)
        return stats

    def verify(self):
        audio_bytes=0; video_bytes=0
        def a(_,__,b):
            nonlocal audio_bytes; audio_bytes+=len(b)
        def v(_,__,b):
            nonlocal video_bytes; video_bytes+=len(b)
        stats=self.play(0,a,v)
        stats.update(audio_bytes=audio_bytes,video_bytes=video_bytes)
        return stats

def main():
    import argparse,json
    ap=argparse.ArgumentParser()
    ap.add_argument("input",type=Path)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    ap.add_argument("--seek-us",type=int,default=0)
    a=ap.parse_args()
    p=AuroraPlayerCore(a.input,a.kephir)
    try:
        start=p.seek_pts(a.seek_us) if a.seek_us else 0
        print(json.dumps(p.play(start),indent=2))
    finally:p.close()

if __name__=="__main__":main()
