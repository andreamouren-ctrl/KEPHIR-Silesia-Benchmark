#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, tempfile, time
from pathlib import Path
import kstream_kmrl_frontend as kmrl

RATE=48000
CH=2
BITS=16
PACKET_MS=2000
OUT=Path("results/benchmarks/audio_classmap_backendaware")

def sha(b): return hashlib.sha256(b).hexdigest()

def khepri_encode(exe,src,arc):
    subprocess.run([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def khepri_decode(exe,arc,outdir):
    if outdir.exists(): shutil.rmtree(outdir)
    subprocess.run([str(exe.resolve()),"dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    if len(files)!=1: raise RuntimeError("unexpected KHEPRI decode output")
    return files[0]

def run_mode(raw_bytes,exe,mode):
    frame_bytes=CH*(BITS//8)
    frames=len(raw_bytes)//frame_bytes
    packet_frames=RATE*PACKET_MS//1000
    frontend_total=0
    backend_total=0
    encode_s=0.0
    decode_s=0.0
    packets=0

    with tempfile.TemporaryDirectory(prefix=f"aurora_{mode}_") as td:
        root=Path(td)
        restored=bytearray()
        for s0 in range(0,frames,packet_frames):
            n=min(packet_frames,frames-s0)
            chunk=raw_bytes[s0*frame_bytes:(s0+n)*frame_bytes]
            src=root/f"{packets}.pcm"
            front=root/f"{packets}.kmrl"
            arc=root/f"{packets}.aur"
            outdir=root/f"{packets}_out"
            dec=root/f"{packets}.dec.pcm"
            src.write_bytes(chunk)

            t=time.perf_counter()
            kmrl.encode_file(src,front,CH,RATE,BITS,20,"adaptive",mode)
            khepri_encode(exe,front,arc)
            encode_s+=time.perf_counter()-t
            frontend_total+=front.stat().st_size
            backend_total+=arc.stat().st_size

            t=time.perf_counter()
            restored_front=khepri_decode(exe,arc,outdir)
            kmrl.decode_file(restored_front,dec)
            decode_s+=time.perf_counter()-t
            got=dec.read_bytes()
            if got!=chunk:
                raise RuntimeError(f"roundtrip failure mode={mode} packet={packets}")
            restored.extend(got)
            packets+=1

    if bytes(restored)!=raw_bytes:
        raise RuntimeError(f"aggregate roundtrip failure {mode}")

    return {
        "mode":mode,
        "packets":packets,
        "frontend_bytes":frontend_total,
        "khepri_bytes":backend_total,
        "ratio_percent":100.0*backend_total/len(raw_bytes),
        "encode_seconds":encode_s,
        "decode_seconds":decode_s,
        "sha_ok":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audio",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,required=True)
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.audio.read_bytes()
    rows=[run_mode(raw,a.kephir,m) for m in ("raw","rle","adaptive")]
    best=min(rows,key=lambda r:r["khepri_bytes"])
    result={
        "experiment":"AURORA audio class-map backend-aware A/B",
        "source_bytes":len(raw),
        "source_sha256":sha(raw),
        "packet_ms":PACKET_MS,
        "rows":rows,
        "best_final_mode":best["mode"],
        "best_final_bytes":best["khepri_bytes"],
    }
    (OUT/"results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    print("BACKENDAWARE_CLASSMAP_PASS")

if __name__=="__main__":
    main()
