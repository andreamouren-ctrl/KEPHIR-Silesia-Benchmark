#!/usr/bin/env python3
import argparse, json, time
from pathlib import Path
import ksv08_threeway_router as k8
import ksv09c_cached_motion_router as k9

OUT=Path("results/video/ksv09d_wallclock")

def parse(s):
    n,p,w,h,fpsn,fpsd,gop=s.split(":")
    return n,Path(p).resolve(),int(w),int(h),int(fpsn),int(fpsd),int(gop)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kephir",type=Path,required=True)
    ap.add_argument("--clip",action="append",required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for spec in a.clip:
        name,src,w,h,fpsn,fpsd,gop=parse(spec)
        o8=OUT/f"{name}_k8.bin"
        o9=OUT/f"{name}_k9.bin"
        t=time.perf_counter()
        k8.encode_file(src,o8,a.kephir,w,h,fpsn,fpsd,gop,20)
        wall8=time.perf_counter()-t
        t=time.perf_counter()
        k9.encode_file(src,o9,a.kephir,w,h,fpsn,fpsd,gop,20)
        wall9=time.perf_counter()-t
        rows.append({
            "name":name,
            "ksv08_bytes":o8.stat().st_size,
            "ksv09c_bytes":o9.stat().st_size,
            "delta_bytes":o9.stat().st_size-o8.stat().st_size,
            "ksv08_wall_seconds":wall8,
            "ksv09c_wall_seconds":wall9,
            "speedup_x":wall8/wall9,
            "wall_reduction_percent":100*(wall8-wall9)/wall8
        })
        print(rows[-1],flush=True)
    result={"experiment":"KSV-09D wall-clock KSV-08 vs KSV-09C","rows":rows}
    result["totals"]={
        "ksv08_bytes":sum(r["ksv08_bytes"] for r in rows),
        "ksv09c_bytes":sum(r["ksv09c_bytes"] for r in rows),
        "ksv08_wall_seconds":sum(r["ksv08_wall_seconds"] for r in rows),
        "ksv09c_wall_seconds":sum(r["ksv09c_wall_seconds"] for r in rows)
    }
    result["totals"]["delta_bytes"]=result["totals"]["ksv09c_bytes"]-result["totals"]["ksv08_bytes"]
    result["totals"]["speedup_x"]=result["totals"]["ksv08_wall_seconds"]/result["totals"]["ksv09c_wall_seconds"]
    result["totals"]["wall_reduction_percent"]=100*(result["totals"]["ksv08_wall_seconds"]-result["totals"]["ksv09c_wall_seconds"])/result["totals"]["ksv08_wall_seconds"]
    (OUT/"KSV09D_RESULTS.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
