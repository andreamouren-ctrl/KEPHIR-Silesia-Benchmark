#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path

from aurora_media_container import (
    AuroraMuxer, AuroraDemuxer, Track,
    TRACK_AUDIO, TRACK_VIDEO,
    CODEC_AURORA_AUDIO, CODEC_AURORA_VIDEO,
    PKT_KEY, PKT_RECOVERY
)
from aurora_media_codec_bridge import (
    encode_audio_packet, decode_audio_packet,
    encode_video_packet, decode_video_packet
)

OUT=Path("results/benchmarks/full_stack_v03")
RATE=48000
ACH=2
ABITS=16
W=176
H=144
FPSN=30000
FPSD=1001
GOP=10
AUDIO_PACKET_MS=200
VIDEO_PACKET_FRAMES=20
FRAME_BYTES=W*H*3//2
TIMESCALE=1_000_000

def sha_bytes(b:bytes): return hashlib.sha256(b).hexdigest()
def sha_file(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def timed(cmd):
    t=time.perf_counter()
    cp=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return cp.returncode,time.perf_counter()-t

def us_audio(samples): return samples*TIMESCALE//RATE
def us_video(frames,fpsn,fpsd): return frames*TIMESCALE*fpsd//fpsn

def aurora_audio_file(raw:Path,exe:Path):
    pcm=raw.read_bytes()
    frame_bytes=ACH*(ABITS//8)
    samples=len(pcm)//frame_bytes
    aps=RATE*AUDIO_PACKET_MS//1000
    out=OUT/"audio_aurora_v03.aum"
    enc_t=0.0
    with AuroraMuxer(out,[Track(1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,RATE,ACH,ABITS,aps)]) as mux:
        for s0 in range(0,samples,aps):
            n=min(aps,samples-s0)
            chunk=pcm[s0*frame_bytes:(s0+n)*frame_bytes]
            t=time.perf_counter(); payload=encode_audio_packet(chunk,exe,ACH,RATE); enc_t+=time.perf_counter()-t
            mux.write_packet(1,us_audio(s0),us_audio(n),payload,PKT_RECOVERY)

    dec=bytearray(); dec_t=0.0
    with AuroraDemuxer(out) as demux:
        for e,p in demux.packets(1):
            t=time.perf_counter(); dec.extend(decode_audio_packet(p,exe)); dec_t+=time.perf_counter()-t
    assert sha_bytes(bytes(dec))==sha_bytes(pcm)
    return dict(codec="AURORA Media v0.3 full AUM",bytes=out.stat().st_size,
                encode_seconds=enc_t,decode_seconds=dec_t,sha_ok=True,
                packets=(samples+aps-1)//aps)

def aurora_video_file(raw:Path,exe:Path,name:str,fpsn:int,fpsd:int):
    yuv=raw.read_bytes(); frames=len(yuv)//FRAME_BYTES
    out=OUT/f"{name}_aurora_v03.aum"
    enc_t=0.0
    with AuroraMuxer(out,[Track(2,TRACK_VIDEO,CODEC_AURORA_VIDEO,0,W,H,fpsn,fpsd)]) as mux:
        for f0 in range(0,frames,VIDEO_PACKET_FRAMES):
            n=min(VIDEO_PACKET_FRAMES,frames-f0)
            chunk=yuv[f0*FRAME_BYTES:(f0+n)*FRAME_BYTES]
            t=time.perf_counter()
            payload=encode_video_packet(chunk,exe,W,H,fpsn,fpsd,GOP,VIDEO_PACKET_FRAMES)
            enc_t+=time.perf_counter()-t
            mux.write_packet(2,us_video(f0,fpsn,fpsd),us_video(n,fpsn,fpsd),
                             payload,PKT_KEY|PKT_RECOVERY)

    dec=bytearray(); dec_t=0.0
    with AuroraDemuxer(out) as demux:
        for e,p in demux.packets(2):
            t=time.perf_counter(); dec.extend(decode_video_packet(p,exe)); dec_t+=time.perf_counter()-t
    assert sha_bytes(bytes(dec))==sha_bytes(yuv)
    return dict(codec="AURORA Media v0.3 full AUM",bytes=out.stat().st_size,
                encode_seconds=enc_t,decode_seconds=dec_t,sha_ok=True,
                packets=(frames+VIDEO_PACKET_FRAMES-1)//VIDEO_PACKET_FRAMES)

def audio_ref(raw:Path,label:str,ext:str,args):
    out=OUT/f"audio_{label}.{ext}"; dec=OUT/f"audio_{label}.raw"
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",
                 "-f","s16le","-ar",str(RATE),"-ac",str(ACH),"-i",str(raw),*args,str(out)])
    if rc: return dict(codec=label,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),
                 "-f","s16le","-ar",str(RATE),"-ac",str(ACH),str(dec)])
    ok=rc==0 and sha_file(dec)==sha_file(raw)
    return dict(codec=label,available=True,bytes=out.stat().st_size,
                encode_seconds=es,decode_seconds=ds,sha_ok=ok)

def video_ref(raw:Path,name:str,fpsn:int,fpsd:int,label:str,args):
    out=OUT/f"{name}_{label}.mkv"; dec=OUT/f"{name}_{label}.yuv"
    inp=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}",
         "-r",f"{fpsn}/{fpsd}","-i",str(raw)]
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*inp,*args,str(out)])
    if rc: return dict(codec=label,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),
                 "-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    ok=rc==0 and sha_file(dec)==sha_file(raw)
    return dict(codec=label,available=True,bytes=out.stat().st_size,
                encode_seconds=es,decode_seconds=ds,sha_ok=ok)

def parse_clip(s):
    name,path,fpsn,fpsd=s.split(":")
    return name,Path(path).resolve(),int(fpsn),int(fpsd)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audio",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)

    raw=a.audio.resolve(); rb=raw.stat().st_size; dur=rb/(RATE*ACH*2)
    audio=[
      aurora_audio_file(raw,a.kephir),
      audio_ref(raw,"FLAC8","flac",["-c:a","flac","-compression_level","8"]),
      audio_ref(raw,"ALAC","m4a",["-c:a","alac"]),
      audio_ref(raw,"WavPack","wv",["-c:a","wavpack","-compression_level","12"]),
    ]
    for r in audio:
        if r.get("available",True) and "bytes" in r:
            r["ratio_percent"]=100*r["bytes"]/rb
            r["encode_realtime_x"]=dur/r["encode_seconds"]
            r["decode_realtime_x"]=dur/r["decode_seconds"]

    videos=[]
    for spec in a.clip:
        name,vraw,fpsn,fpsd=parse_clip(spec)
        rawb=vraw.stat().st_size; frames=rawb//FRAME_BYTES; durv=frames*fpsd/fpsn
        rows=[
          aurora_video_file(vraw,a.kephir,name,fpsn,fpsd),
          video_ref(vraw,name,fpsn,fpsd,"FFV1",["-c:v","ffv1","-level","3","-coder","1","-context","1","-g",str(GOP)]),
          video_ref(vraw,name,fpsn,fpsd,"H264_lossless",["-c:v","libx264","-preset","medium","-qp","0","-g",str(GOP)]),
          video_ref(vraw,name,fpsn,fpsd,"HEVC_lossless",["-c:v","libx265","-preset","medium","-x265-params",f"lossless=1:keyint={GOP}:log-level=error"]),
          video_ref(vraw,name,fpsn,fpsd,"VP9_lossless",["-c:v","libvpx-vp9","-lossless","1","-deadline","good","-cpu-used","2","-g",str(GOP)]),
          video_ref(vraw,name,fpsn,fpsd,"AV1_lossless",["-c:v","libaom-av1","-crf","0","-b:v","0","-cpu-used","6","-g",str(GOP)]),
        ]
        for r in rows:
            if r.get("available",True) and "bytes" in r:
                r["ratio_percent"]=100*r["bytes"]/rawb
                r["bits_per_pixel"]=8*r["bytes"]/(W*H*frames)
                r["encode_realtime_x"]=durv/r["encode_seconds"]
                r["decode_realtime_x"]=durv/r["decode_seconds"]
        videos.append(dict(name=name,raw_bytes=rawb,frames=frames,fps=f"{fpsn}/{fpsd}",rows=rows))

    result={
      "experiment":"AURORA full-stack container benchmark v0.3",
      "scope":"Final file sizes including AUM/MKV/codec container overhead",
      "audio_source":{"bytes":rb,"seconds":dur,"sha256":sha_file(raw)},
      "audio":audio,
      "video":videos,
      "aurora":{"container":"AUM v0.1","backend":"EXP-37A","audio_packet_ms":AUDIO_PACKET_MS,
                "video_packet_frames":VIDEO_PACKET_FRAMES,"video_router":"KSV-05 20-frame horizon"},
      "notes":["All lossless outputs are SHA verified.","AURORA timing still includes Python frontend and subprocess KHEPRI staging."]
    }
    p=OUT/"full_stack_results.json"; p.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
