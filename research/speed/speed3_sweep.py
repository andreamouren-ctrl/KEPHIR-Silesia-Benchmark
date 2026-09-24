from pathlib import Path
import subprocess,time,json,hashlib,shutil,statistics,sys,os
ROOT=Path("silesia"); OUT=Path("speed3_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
PROFILES=[
 ("FAST_C6","./fast_c",6),
 ("FAST_D6","./fast_d",6),
 ("FAST_E6","./fast_e",6),
 ("FAST_D8","./fast_d",8),
 ("FAST_E8","./fast_e",8),
]
rows=[]
for tag,exe,thr in PROFILES:
    tr=ts=tc=td=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{tag}_{fn}.aur"; dec=OUT/f"d_{tag}_{fn}"
        cts=[]; dts=[]
        for _ in range(3):
            if arc.exists(): arc.unlink()
            t=time.perf_counter()
            subprocess.run([exe,"cp",str(p),str(arc),str(thr),"6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cts.append(time.perf_counter()-t)
        size=arc.stat().st_size
        for _ in range(3):
            if dec.exists(): shutil.rmtree(dec)
            t=time.perf_counter()
            subprocess.run([exe,"dp",str(arc),str(dec),str(thr)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            dts.append(time.perf_counter()-t)
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("SHA FAIL "+tag+" "+fn)
        tr+=raw; ts+=size; tc+=statistics.median(cts); td+=statistics.median(dts)
    rows.append(dict(profile=tag,threads=thr,raw=int(tr),size=int(ts),ratio=100*ts/tr,
                     comp_MBps=(tr/1e6)/tc,dec_MBps=(tr/1e6)/td,sha=True))
print("SUMMARY")
for r in rows: print(r,flush=True)
Path("speed3_results.json").write_text(json.dumps(rows,indent=2))
