#!/usr/bin/env python3
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path

import kstream_kmrl_lab as lab
from ks06_plane_sparsity_bench import enc_tail16, dec_tail16
from kstream_video_baseline import encode_file as vbase_encode, decode_file as vbase_decode
from kstream_video_mc import encode_file as vmc_encode, decode_file as vmc_decode

OUT=Path("streaming/major_codec_bench_out")
RATE=48000; ACH=2; ABITS=16
W=176; H=144; GOP=10; RADIUS=4
FRAME_BYTES=W*H*3//2

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def timed(cmd):
    t=time.perf_counter()
    cp=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return cp.returncode,time.perf_counter()-t

def have_encoder(name):
    cp=subprocess.run(["ffmpeg","-hide_banner","-encoders"],capture_output=True,text=True)
    return name in cp.stdout

def aurora_audio(raw,exe):
    front=OUT/"aurora_audio.front"; restored=OUT/"aurora_audio_front.raw"
    oe,od=lab.enc_fullplanes,lab.dec_fullplanes
    lab.enc_fullplanes,lab.dec_fullplanes=enc_tail16,dec_tail16
    try:
        t=time.perf_counter(); lab.encode_file(raw,front,ACH,RATE,20,2); fe=time.perf_counter()-t
        t=time.perf_counter(); lab.decode_file(front,restored); fd=time.perf_counter()-t
    finally:
        lab.enc_fullplanes,lab.dec_fullplanes=oe,od
    assert sha(restored)==sha(raw)
    arc=OUT/"aurora_audio.aur"; decdir=OUT/"aurora_audio_dec"
    if decdir.exists(): shutil.rmtree(decdir)
    rc,ke=timed([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"]); assert rc==0
    rc,kd=timed([str(exe.resolve()),"dp",str(arc),str(decdir),"6"]); assert rc==0
    assert sha(decdir/front.name)==sha(front)
    return dict(codec="AURORA/KHEPRI KMRL+TAIL16+EXP37A",bytes=arc.stat().st_size,
                encode_seconds=fe+ke,decode_seconds=fd+kd,sha_ok=True)

def audio_ffmpeg(raw,codec,ext,args):
    out=OUT/f"audio_{codec}.{ext}"; dec=OUT/f"audio_{codec}.raw"
    common=["-f","s16le","-ar",str(RATE),"-ac",str(ACH),"-i",str(raw)]
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*common,*args,str(out)])
    if rc: return dict(codec=codec,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),"-f","s16le","-ar",str(RATE),"-ac",str(ACH),str(dec)])
    ok=(rc==0 and sha(dec)==sha(raw))
    return dict(codec=codec,available=True,bytes=out.stat().st_size,encode_seconds=es,decode_seconds=ds,sha_ok=ok)

def audio_lossy(raw,codec,label,args):
    out=OUT/f"audio_lossy_{label}.mka"; dec=OUT/f"audio_lossy_{label}.raw"
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","s16le","-ar",str(RATE),"-ac",str(ACH),"-i",str(raw),*args,str(out)])
    if rc: return dict(codec=codec,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),"-f","s16le","-ar",str(RATE),"-ac",str(ACH),str(dec)])
    return dict(codec=codec,available=rc==0,bytes=out.stat().st_size,encode_seconds=es,decode_seconds=ds)

def kvideo_front(raw,name,fpsn,fpsd,kind,exe):
    front=OUT/f"{name}_{kind}.front"; restored=OUT/f"{name}_{kind}.raw"
    if kind=="TEMP":
        t=time.perf_counter(); vbase_encode(raw,front,W,H,fpsn,fpsd,GOP,3); fe=time.perf_counter()-t
        t=time.perf_counter(); vbase_decode(front,restored); fd=time.perf_counter()-t
    else:
        t=time.perf_counter(); vmc_encode(raw,front,W,H,fpsn,fpsd,GOP,8,RADIUS); fe=time.perf_counter()-t
        t=time.perf_counter(); vmc_decode(front,restored); fd=time.perf_counter()-t
    assert sha(restored)==sha(raw)
    arc=OUT/f"{name}_{kind}.aur"; decdir=OUT/f"{name}_{kind}_dec"
    if decdir.exists(): shutil.rmtree(decdir)
    rc,ke=timed([str(exe.resolve()),"cp",str(front),str(arc),"6","6.55","9.42","1.20"]); assert rc==0
    rc,kd=timed([str(exe.resolve()),"dp",str(arc),str(decdir),"6"]); assert rc==0
    assert sha(decdir/front.name)==sha(front)
    return dict(codec=f"AURORA/KHEPRI {kind}+EXP37A",bytes=arc.stat().st_size,
                encode_seconds=fe+ke,decode_seconds=fd+kd,sha_ok=True)

def video_lossless(raw,name,fpsn,fpsd,label,enc_args):
    out=OUT/f"{name}_{label}.mkv"; dec=OUT/f"{name}_{label}.yuv"
    inp=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}","-r",f"{fpsn}/{fpsd}","-i",str(raw)]
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*inp,*enc_args,str(out)])
    if rc: return dict(codec=label,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),"-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    ok=(rc==0 and sha(dec)==sha(raw))
    return dict(codec=label,available=True,bytes=out.stat().st_size,encode_seconds=es,decode_seconds=ds,sha_ok=ok)

def video_lossy(raw,name,fpsn,fpsd,label,enc_args):
    out=OUT/f"{name}_{label}.mkv"; dec=OUT/f"{name}_{label}.yuv"
    inp=["-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}","-r",f"{fpsn}/{fpsd}","-i",str(raw)]
    rc,es=timed(["ffmpeg","-hide_banner","-loglevel","error","-y",*inp,*enc_args,str(out)])
    if rc: return dict(codec=label,available=False)
    rc,ds=timed(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(out),"-pix_fmt","yuv420p","-f","rawvideo",str(dec)])
    if rc: return dict(codec=label,available=False)
    # PSNR through ffmpeg filter; parse stderr.
    cp=subprocess.run(["ffmpeg","-hide_banner","-i",str(out),"-f","rawvideo","-pix_fmt","yuv420p","-s:v",f"{W}x{H}","-r",f"{fpsn}/{fpsd}","-i",str(raw),"-lavfi","psnr","-f","null","-"],capture_output=True,text=True)
    psnr=None
    for line in cp.stderr.splitlines()[::-1]:
        if "average:" in line and "PSNR" in line:
            try: psnr=float(line.split("average:")[1].split()[0])
            except: pass
            break
    return dict(codec=label,available=True,bytes=out.stat().st_size,encode_seconds=es,decode_seconds=ds,psnr_db=psnr)

def parse_clip(s):
    n,p,a,b=s.split(":"); return n,Path(p).resolve(),int(a),int(b)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audio",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir37"))
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    raw=a.audio.resolve(); rb=raw.stat().st_size; dur=rb/(RATE*ACH*2)
    audio=[
      aurora_audio(raw,a.kephir),
      audio_ffmpeg(raw,"FLAC","flac",["-c:a","flac","-compression_level","8"]),
      audio_ffmpeg(raw,"ALAC","m4a",["-c:a","alac"]),
      audio_ffmpeg(raw,"WavPack","wv",["-c:a","wavpack","-compression_level","12"]),
    ]
    for r in audio:
        if r.get("available",True) and "bytes" in r:
            r["ratio_to_pcm_percent"]=100*r["bytes"]/rb
            r["encode_realtime_x"]=dur/r["encode_seconds"]
            r["decode_realtime_x"]=dur/r["decode_seconds"]
    audio_stream=[
      audio_lossy(raw,"Opus 128 kb/s","opus128",["-c:a","libopus","-b:a","128k","-vbr","on"]),
      audio_lossy(raw,"AAC 128 kb/s","aac128",["-c:a","aac","-b:a","128k"]),
    ]

    clips=[]
    for spec in a.clip:
        name,vraw,fpsn,fpsd=parse_clip(spec); vb=vraw.stat().st_size; frames=vb//FRAME_BYTES; vdur=frames*fpsd/fpsn
        rows=[
          kvideo_front(vraw,name,fpsn,fpsd,"TEMP",a.kephir),
          kvideo_front(vraw,name,fpsn,fpsd,"MC8R4",a.kephir),
          video_lossless(vraw,name,fpsn,fpsd,"FFV1",["-c:v","ffv1","-level","3","-coder","1","-context","1","-g",str(GOP)]),
          video_lossless(vraw,name,fpsn,fpsd,"H264_lossless",["-c:v","libx264","-preset","medium","-qp","0","-g",str(GOP)]),
          video_lossless(vraw,name,fpsn,fpsd,"HEVC_lossless",["-c:v","libx265","-preset","medium","-x265-params",f"lossless=1:keyint={GOP}:log-level=error"]),
          video_lossless(vraw,name,fpsn,fpsd,"VP9_lossless",["-c:v","libvpx-vp9","-lossless","1","-deadline","good","-cpu-used","2","-g",str(GOP)]),
          video_lossless(vraw,name,fpsn,fpsd,"AV1_lossless",["-c:v","libaom-av1","-crf","0","-b:v","0","-cpu-used","6","-g",str(GOP)]),
        ]
        for r in rows:
            if r.get("available",True) and "bytes" in r:
                r["ratio_to_raw_percent"]=100*r["bytes"]/vb
                r["bits_per_pixel"]=8*r["bytes"]/(W*H*frames)
                r["encode_realtime_x"]=vdur/r["encode_seconds"]
                r["decode_realtime_x"]=vdur/r["decode_seconds"]
        lossy=[
          video_lossy(vraw,name,fpsn,fpsd,"H264_300k",["-c:v","libx264","-preset","medium","-b:v","300k","-g",str(GOP)]),
          video_lossy(vraw,name,fpsn,fpsd,"HEVC_300k",["-c:v","libx265","-preset","medium","-b:v","300k","-x265-params",f"keyint={GOP}:log-level=error"]),
          video_lossy(vraw,name,fpsn,fpsd,"VP9_300k",["-c:v","libvpx-vp9","-b:v","300k","-deadline","good","-cpu-used","2","-g",str(GOP)]),
          video_lossy(vraw,name,fpsn,fpsd,"AV1_300k",["-c:v","libaom-av1","-b:v","300k","-cpu-used","6","-g",str(GOP)]),
        ]
        clips.append({"name":name,"raw_bytes":vb,"frames":frames,"fps":f"{fpsn}/{fpsd}","lossless":rows,"lossy_300k":lossy})

    result={"experiment":"AURORA/KHEPRI major codec benchmark","audio_source":{"bytes":rb,"seconds":dur,"sha256":sha(raw)},
            "audio_lossless":audio,"audio_streaming_reference":audio_stream,"video_clips":clips,
            "notes":["Lossless comparisons require bit-exact reconstruction.","Lossy references are separate and are not ranked against AURORA lossless."]}
    (OUT/"major_codec_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
