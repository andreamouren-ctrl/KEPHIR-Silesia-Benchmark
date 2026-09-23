#!/usr/bin/env python3
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
import kstream_kmrl_lab as lab

OUT=Path("streaming/ks05_out")
RATE=48000
CHANNELS=2
BLOCK_MS=20
LAYOUT=2  # FULL256


def sha(p:Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def timed(cmd):
    t=time.perf_counter()
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t


def topo_hits(buf:bytes):
    h16=sum(1 for i in range(16,len(buf)) if buf[i]==buf[i-16])
    h256=sum(1 for i in range(256,len(buf)) if buf[i]==buf[i-256])
    return h16,h256


def make_choose(policy):
    def choose(values, initial_hist):
        cands=[]
        for mode in (0,1,2):
            us=[lab.zz_enc(r) for r in lab.residuals(values,mode,initial_hist)]
            class_cost=lab.class_cost(us)
            physical=lab.enc_fullplanes(us,False)
            h16,h256=topo_hits(physical)

            if policy=="CLASS_BASE":
                score=float(class_cost)
            elif policy=="PLANE_BYTES":
                score=float(len(physical))
            elif policy=="TOPO_16_256":
                # Small topology pressure only. The individual predictor
                # formulas are background; the research object is backend-aware
                # predictor selection for KHEPRI's native recurrence scales.
                score=float(len(physical)) - 0.10*h16 - 0.22*h256
            else:
                raise ValueError(policy)
            cands.append((score,len(physical),class_cost,mode,us))
        _,_,_,mode,us=min(cands,key=lambda x:(x[0],x[1],x[2],x[3]))
        return (lab.class_cost(us),mode,us)
    return choose


def kephir(exe:Path,src:Path,tag:str):
    arc=OUT/f"{tag}.aur"
    dec=OUT/f"dec_{tag}"
    if arc.exists(): arc.unlink()
    if dec.exists(): shutil.rmtree(dec)
    es=timed([str(exe.resolve()),"cp",str(src),str(arc),"6","6.55","9.42","1.20"])
    ds=timed([str(exe.resolve()),"dp",str(arc),str(dec),"6"])
    restored=dec/src.name
    if sha(restored)!=sha(src):
        raise SystemExit(f"KEPHIR SHA FAIL {tag}")
    return arc.stat().st_size,es,ds


def run_variant(exe,raw,tag,policy):
    old=lab.choose
    lab.choose=make_choose(policy)
    try:
        front=OUT/f"{tag}.front"
        restored=OUT/f"{tag}.raw"

        t=time.perf_counter()
        lab.encode_file(raw,front,CHANNELS,RATE,BLOCK_MS,LAYOUT)
        fe=time.perf_counter()-t

        t=time.perf_counter()
        lab.decode_file(front,restored)
        fd=time.perf_counter()-t
        if sha(restored)!=sha(raw):
            raise SystemExit(f"FRONTEND SHA FAIL {tag}")

        kb,ke,kd=kephir(exe,front,tag)
        return {
            "codec":tag,
            "policy":policy,
            "frontend_bytes":front.stat().st_size,
            "bytes":kb,
            "frontend_encode_seconds":fe,
            "frontend_decode_seconds":fd,
            "backend_encode_seconds":ke,
            "backend_decode_seconds":kd,
            "sha_ok":True,
        }
    finally:
        lab.choose=old


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",type=Path,required=True)
    ap.add_argument("--kephir",type=Path,default=Path("./kephir33"))
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    raw=a.raw.resolve()
    raw_bytes=raw.stat().st_size
    duration=raw_bytes/(RATE*CHANNELS*2)

    variants=[
        ("FULL256_CLASS_BASE","CLASS_BASE"),
        ("FULL256_PLANE_BYTES","PLANE_BYTES"),
        ("FULL256_TOPO_16_256","TOPO_16_256"),
    ]
    rows=[run_variant(a.kephir,raw,*v) for v in variants]
    base=rows[0]["bytes"]
    for r in rows:
        r["ratio_to_pcm_percent"]=100*r["bytes"]/raw_bytes
        r["delta_vs_base_bytes"]=r["bytes"]-base
        r["delta_vs_base_percent"]=100*(r["bytes"]-base)/base
        r["encode_realtime_x"]=duration/(r["frontend_encode_seconds"]+r["backend_encode_seconds"])
        r["decode_realtime_x"]=duration/(r["frontend_decode_seconds"]+r["backend_decode_seconds"])

    result={
        "experiment":"KS-05 backend-aware predictor selection on FULL256",
        "source":{"bytes":raw_bytes,"duration_seconds":duration,"sha256":sha(raw),
                  "profile":"Sintel-derived stereo s16le 48kHz"},
        "block_ms":BLOCK_MS,
        "layout":"FULL256",
        "rows":rows,
        "promotion_rule":"Promote only if final EXP-33H bytes improve and reconstruction remains bit-exact."
    }
    (OUT/"ks05_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
