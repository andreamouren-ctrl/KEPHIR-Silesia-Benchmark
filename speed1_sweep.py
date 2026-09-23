from pathlib import Path
import subprocess,time,json,hashlib,shutil,statistics

ROOT=Path("silesia"); OUT=Path("speed1_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
PROFILES=[
 ("FAST_A","./kephir_fast_a"),
 ("FAST_B","./kephir_fast_b"),
 ("FAST_C","./kephir_fast_c"),
]
rows=[]
for tag,exe in PROFILES:
    total_raw=total_size=0; ct=dt=0.0
    print("\nPROFILE",tag,flush=True)
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{tag}_{fn}.aur"; dec=OUT/f"dec_{tag}_{fn}"
        ctimes=[]; dtimes=[]
        for _ in range(3):
            if arc.exists(): arc.unlink()
            t=time.perf_counter()
            subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            ctimes.append(time.perf_counter()-t)
        size=arc.stat().st_size
        for _ in range(3):
            if dec.exists(): shutil.rmtree(dec)
            t=time.perf_counter()
            subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            dtimes.append(time.perf_counter()-t)
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("SHA FAIL "+tag+" "+fn)
        mc=statistics.median(ctimes); md=statistics.median(dtimes)
        total_raw+=raw; total_size+=size; ct+=mc; dt+=md
        print(dict(file=fn,size=size,comp=raw/1e6/mc,dec=raw/1e6/md),flush=True)
    rows.append(dict(profile=tag,raw=total_raw,size=total_size,ratio=100*total_size/total_raw,
                     comp_MBps=(total_raw/1e6)/ct,dec_MBps=(total_raw/1e6)/dt,sha=True))
print("\nSUMMARY")
for r in rows: print(r,flush=True)
Path("speed1_results.json").write_text(json.dumps(rows,indent=2))
