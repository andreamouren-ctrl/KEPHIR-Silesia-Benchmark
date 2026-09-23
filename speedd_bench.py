from pathlib import Path
import subprocess,time,json,hashlib,shutil,statistics
ROOT=Path("silesia"); OUT=Path("speedd_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
rawtot=sizetot=0;ct=dt=0.0
for fn in FILES:
    p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{fn}.aur"; dec=OUT/f"dec_{fn}"
    cs=[];ds=[]
    for _ in range(3):
        if arc.exists():arc.unlink()
        t=time.perf_counter()
        subprocess.run(["./kephir_fast_d","cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cs.append(time.perf_counter()-t)
    size=arc.stat().st_size
    for _ in range(3):
        if dec.exists():shutil.rmtree(dec)
        t=time.perf_counter()
        subprocess.run(["./kephir_fast_d","dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ds.append(time.perf_counter()-t)
    ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
    if not ok: raise SystemExit("SHA FAIL "+fn)
    mc=statistics.median(cs);md=statistics.median(ds)
    rawtot+=raw;sizetot+=size;ct+=mc;dt+=md
    print(dict(file=fn,size=size,comp=raw/1e6/mc,dec=raw/1e6/md),flush=True)
summary=dict(profile="FAST_D_LITERAL_BYPASS",raw=rawtot,size=sizetot,ratio=100*sizetot/rawtot,
             comp_MBps=(rawtot/1e6)/ct,dec_MBps=(rawtot/1e6)/dt,sha=True)
print("SUMMARY",summary,flush=True)
Path("speedd_results.json").write_text(json.dumps(summary,indent=2))
