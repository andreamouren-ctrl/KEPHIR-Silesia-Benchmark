#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, tempfile, time
from pathlib import Path

import kstream_kmrl_frontend as v2
import kstream_kmrl_lab as legacy
from ks06_plane_sparsity import enc_tail16, dec_tail16

RATE=48000
CH=2
BITS=16
PACKET_MS=2000
OUT=Path("results/benchmarks/audio_pipeline_ab_v01")

def sha_bytes(b): return hashlib.sha256(b).hexdigest()

def khepri_encode(exe, src, arc):
    t=time.perf_counter()
    subprocess.run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def khepri_decode(exe, arc, outdir):
    if outdir.exists(): shutil.rmtree(outdir)
    t=time.perf_counter()
    subprocess.run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    dt=time.perf_counter()-t
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1: raise RuntimeError("unexpected KHEPRI decode output")
    return files[0],dt

def legacy_front_encode(raw,front):
    oe,od=legacy.enc_fullplanes,legacy.dec_fullplanes
    legacy.enc_fullplanes,legacy.dec_fullplanes=enc_tail16,dec_tail16
    try:
        legacy.encode_file(raw,front,CH,RATE,20,2)
    finally:
        legacy.enc_fullplanes,legacy.dec_fullplanes=oe,od

def legacy_front_decode(front,raw):
    oe,od=legacy.enc_fullplanes,legacy.dec_fullplanes
    legacy.enc_fullplanes,legacy.dec_fullplanes=enc_tail16,dec_tail16
    try:
        legacy.decode_file(front,raw)
    finally:
        legacy.enc_fullplanes,legacy.dec_fullplanes=oe,od

def v2_front_encode(raw,front,classmap):
    v2.encode_file(raw,front,CH,RATE,BITS,20,"adaptive",classmap)

def v2_front_decode(front,raw):
    v2.decode_file(front,raw)

def run_packetized(pcm,exe,name,front_kind):
    frame_bytes=CH*(BITS//8)
    total_frames=len(pcm)//frame_bytes
    packet_frames=RATE*PACKET_MS//1000
    total_front=total_backend=0
    front_enc=front_dec=backend_enc=backend_dec=0.0
    restored=bytearray()
    with tempfile.TemporaryDirectory(prefix="aua_ab_") as td:
        t=Path(td)
        pi=0
        for s0 in range(0,total_frames,packet_frames):
            n=min(packet_frames,total_frames-s0)
            raw=t/f"p{pi}.pcm"; front=t/f"p{pi}.front"; arc=t/f"p{pi}.aur"; out=t/f"out{pi}"; dec=t/f"p{pi}.dec"
            chunk=pcm[s0*frame_bytes:(s0+n)*frame_bytes]
            raw.write_bytes(chunk)
            if front_kind=="legacy":
                ts=time.perf_counter(); legacy_front_encode(raw,front); front_enc+=time.perf_counter()-ts
            elif front_kind=="v2_raw":
                ts=time.perf_counter(); v2_front_encode(raw,front,"raw"); front_enc+=time.perf_counter()-ts
            elif front_kind=="v2_adaptive":
                ts=time.perf_counter(); v2_front_encode(raw,front,"adaptive"); front_enc+=time.perf_counter()-ts
            elif front_kind=="pcm":
                shutil.copyfile(raw,front)
            else: raise ValueError(front_kind)

            total_front+=front.stat().st_size
            backend_enc+=khepri_encode(exe,front,arc)
            total_backend+=arc.stat().st_size
            restored_front,dt=khepri_decode(exe,arc,out); backend_dec+=dt
            if front_kind=="legacy":
                ts=time.perf_counter(); legacy_front_decode(restored_front,dec); front_dec+=time.perf_counter()-ts
                restored.extend(dec.read_bytes())
            elif front_kind.startswith("v2_"):
                ts=time.perf_counter(); v2_front_decode(restored_front,dec); front_dec+=time.perf_counter()-ts
                restored.extend(dec.read_bytes())
            else:
                restored.extend(restored_front.read_bytes())
            pi+=1
    if bytes(restored)!=pcm: raise RuntimeError(f"roundtrip failed: {name}")
    return dict(name=name,packet_ms=PACKET_MS,packets=pi,front_bytes=total_front,
                backend_bytes=total_backend,front_encode_seconds=front_enc,
                backend_encode_seconds=backend_enc,front_decode_seconds=front_dec,
                backend_decode_seconds=backend_dec,sha_ok=True)

def run_whole(pcm,exe):
    with tempfile.TemporaryDirectory(prefix="aua_whole_") as td:
        t=Path(td); raw=t/"whole.pcm"; front=t/"whole.kmrl"; arc=t/"whole.aur"; out=t/"out"; dec=t/"dec.pcm"
        raw.write_bytes(pcm)
        ts=time.perf_counter(); v2_front_encode(raw,front,"adaptive"); fe=time.perf_counter()-ts
        be=khepri_encode(exe,front,arc)
        restored_front,bd=khepri_decode(exe,arc,out)
        ts=time.perf_counter(); v2_front_decode(restored_front,dec); fd=time.perf_counter()-ts
        if dec.read_bytes()!=pcm: raise RuntimeError("whole roundtrip failed")
        return dict(name="v2_adaptive_whole",packet_ms=None,packets=1,
                    front_bytes=front.stat().st_size,backend_bytes=arc.stat().st_size,
                    front_encode_seconds=fe,backend_encode_seconds=be,
                    front_decode_seconds=fd,backend_decode_seconds=bd,sha_ok=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audio",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,required=True)
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    pcm=a.audio.read_bytes()
    rows=[
        run_packetized(pcm,a.kephir,"legacy_tail16_packet2s","legacy"),
        run_packetized(pcm,a.kephir,"v2_raw_packet2s","v2_raw"),
        run_packetized(pcm,a.kephir,"v2_adaptive_packet2s","v2_adaptive"),
        run_packetized(pcm,a.kephir,"pcm_direct_packet2s","pcm"),
        run_whole(pcm,a.kephir),
    ]
    for r in rows:
        r["front_ratio_percent"]=100*r["front_bytes"]/len(pcm)
        r["backend_ratio_percent"]=100*r["backend_bytes"]/len(pcm)
        r["encode_seconds"]=r["front_encode_seconds"]+r["backend_encode_seconds"]
        r["decode_seconds"]=r["front_decode_seconds"]+r["backend_decode_seconds"]
        print("AUDIO_PIPELINE_AB",json.dumps(r,sort_keys=True))
    result={"experiment":"AURORA audio pipeline A/B v0.1","source_bytes":len(pcm),
            "source_sha256":sha_bytes(pcm),"rows":rows}
    (OUT/"results.json").write_text(json.dumps(result,indent=2))
    print("AUDIO_PIPELINE_AB_PASS rows=5")

if __name__=="__main__":
    main()
