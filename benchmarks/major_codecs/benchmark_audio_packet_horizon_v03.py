#!/usr/bin/env python3
import argparse, hashlib, json, time
from pathlib import Path
from aurora_media_container import AuroraMuxer,AuroraDemuxer,Track,TRACK_AUDIO,CODEC_AURORA_AUDIO,PKT_RECOVERY
from aurora_media_codec_bridge import encode_audio_packet,decode_audio_packet

RATE=48000; CH=2; BITS=16; TS=1_000_000
OUT=Path("results/audio/packet_horizon_v03")

def sha(b): return hashlib.sha256(b).hexdigest()
def us(samples): return samples*TS//RATE

def run(raw,exe,ms):
    pcm=raw.read_bytes(); fb=CH*(BITS//8); samples=len(pcm)//fb; aps=RATE*ms//1000
    out=OUT/f"audio_{ms}ms.aum"; et=dt=0.0
    with AuroraMuxer(out,[Track(1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,RATE,CH,BITS,aps)]) as mux:
        for s0 in range(0,samples,aps):
            n=min(aps,samples-s0); chunk=pcm[s0*fb:(s0+n)*fb]
            t=time.perf_counter(); payload=encode_audio_packet(chunk,exe,CH,RATE); et+=time.perf_counter()-t
            mux.write_packet(1,us(s0),us(n),payload,PKT_RECOVERY)
    dec=bytearray()
    with AuroraDemuxer(out) as d:
        for e,p in d.packets(1):
            t=time.perf_counter(); dec.extend(decode_audio_packet(p,exe)); dt+=time.perf_counter()-t
    assert sha(bytes(dec))==sha(pcm)
    packets=(samples+aps-1)//aps
    pure_container=16+20+8+24+packets*(32+32)
    return dict(packet_ms=ms,packets=packets,bytes=out.stat().st_size,
                ratio_percent=100*out.stat().st_size/len(pcm),
                estimated_container_metadata_bytes=pure_container,
                encode_seconds=et,decode_seconds=dt,sha_ok=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--audio",type=Path,required=True); ap.add_argument("--kephir",type=Path,required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    rows=[run(a.audio.resolve(),a.kephir,m) for m in (200,500,1000,2000)]
    result={"experiment":"AURORA audio packet horizon v0.3","rows":rows}
    (OUT/"results.json").write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=="__main__": main()
