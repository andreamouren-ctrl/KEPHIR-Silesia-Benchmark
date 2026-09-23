#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

from kstream_video_mc import encode_file as raster_encode
from kstream_video_lattice import encode_file as lattice_encode

OUT=Path("streaming/ksvd01_out")
W=176; H=144; GOP=10; RADIUS=4
FRAME_BYTES=W*H + 2*((W+1)//2)*((H+1)//2)
DISTANCES=(15,16,17,255,256,257,512,768,1024)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_stats(data: bytes, dist: int):
    n=len(data)
    if n<=dist:
        return dict(distance=dist,equality_fraction=0.0,runs4=0,run_bytes4=0,
                    max_run=0,run_bytes4_fraction=0.0)
    eq=0
    runs4=0
    run_bytes4=0
    max_run=0
    run=0
    for i in range(dist,n):
        if data[i]==data[i-dist]:
            eq+=1
            run+=1
        else:
            if run>=4:
                runs4+=1
                run_bytes4+=run
                max_run=max(max_run,run)
            run=0
    if run>=4:
        runs4+=1
        run_bytes4+=run
        max_run=max(max_run,run)
    denom=n-dist
    return dict(
        distance=dist,
        equality_fraction=eq/denom,
        runs4=runs4,
        run_bytes4=run_bytes4,
        max_run=max_run,
        run_bytes4_fraction=run_bytes4/denom,
    )


def aggregate(stats):
    native=[s for s in stats if s["distance"] in (15,16,17,255,256,257)]
    return dict(
        native_equality_sum=sum(s["equality_fraction"] for s in native),
        native_run_bytes4_sum=sum(s["run_bytes4"] for s in native),
        native_runs4_sum=sum(s["runs4"] for s in native),
        d16_run_bytes4=sum(s["run_bytes4"] for s in stats if s["distance"] in (15,16,17)),
        d256_run_bytes4=sum(s["run_bytes4"] for s in stats if s["distance"] in (255,256,257)),
    )


def inspect(path:Path):
    data=path.read_bytes()
    stats=[run_stats(data,d) for d in DISTANCES]
    return dict(bytes=len(data),sha256=sha(path),distances=stats,aggregate=aggregate(stats))


def parse_clip(s):
    name,path,fpsn,fpsd=s.split(":",3)
    return name,Path(path).resolve(),int(fpsn),int(fpsd)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)

    clips=[]
    for spec in a.clip:
        name,raw,fpsn,fpsd=parse_clip(spec)
        if raw.stat().st_size%FRAME_BYTES:
            raise SystemExit(f"bad raw video {name}")

        variants=[]
        for block in (16,8):
            for layout,enc in (("RASTER",raster_encode),("LATTICE",lattice_encode)):
                p=OUT/f"{name}_MC{block}_{layout}.front"
                enc(raw,p,W,H,fpsn,fpsd,GOP,block,RADIUS)
                variants.append(dict(
                    variant=f"MC{block}_R4_{layout}",
                    **inspect(p),
                ))
        clips.append(dict(name=name,source_sha256=sha(raw),variants=variants))

    result=dict(
        experiment="KSV-D01 favored-distance matchability diagnostic",
        distances=list(DISTANCES),
        clips=clips,
        note="Diagnostic only. Equality/run statistics are proxies and do not reproduce the full EXP-33H parser.",
    )
    (OUT/"ksvd01_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
