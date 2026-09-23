from pathlib import Path
import subprocess,time,json,hashlib,shutil,statistics
ROOT=Path("silesia"); OUT=Path("fastk_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
PROFILES=[("FAST_H","./fast_h"),("FAST_K","./fast_k")]
rows=[]
for tag,exe in PROFILES:
    tr=ts=0; tc=td=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{tag}_{fn}.aur"; dec=OUT/f"d_{tag}_{fn}"
        cts=[]; dts=[]
        for _ in range(3):
            if arc.exists(): arc.unlink()
            t=time.perf_counter()
            subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cts.append(time.perf_counter()-t)
        size=arc.stat().st_size
        for _ in range(3):
            if dec.exists(): shutil.rmtree(dec)
            t=time.perf_counter()
            subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            dts.append(time.perf_counter()-t)
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("SHA FAIL "+tag+" "+fn)
        tr+=raw; ts+=size; tc+=statistics.median(cts); td+=statistics.median(dts)
    rows.append(dict(profile=tag,raw=tr,size=ts,ratio=100*ts/tr,
                     comp_MBps=(tr/1e6)/tc,dec_MBps=(tr/1e6)/td,sha=True))
print("SUMMARY")
for r in rows: print(r,flush=True)
Path("fastk_results.json").write_text(json.dumps(rows,indent=2))
