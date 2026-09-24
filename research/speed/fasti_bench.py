from pathlib import Path
import subprocess,time,json,hashlib,shutil,statistics
ROOT=Path("silesia"); OUT=Path("fasti_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
PROFILES=[("FAST_D","./kephir_fast_d"),("FAST_I","./kephir_fast_i")]
rows=[]
for tag,exe in PROFILES:
    rawtot=sizetot=0; ct=dt=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{tag}_{fn}.aur"; dec=OUT/f"d_{tag}_{fn}"
        cs=[]; ds=[]
        for _ in range(3):
            if arc.exists(): arc.unlink()
            t=time.perf_counter()
            subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cs.append(time.perf_counter()-t)
        size=arc.stat().st_size
        for _ in range(3):
            if dec.exists(): shutil.rmtree(dec)
            t=time.perf_counter()
            subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            ds.append(time.perf_counter()-t)
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("SHA FAIL "+tag+" "+fn)
        rawtot+=raw; sizetot+=size; ct+=statistics.median(cs); dt+=statistics.median(ds)
    rows.append(dict(profile=tag,raw=rawtot,size=sizetot,ratio=100*sizetot/rawtot,
                     comp_MBps=(rawtot/1e6)/ct,dec_MBps=(rawtot/1e6)/dt,sha=True))
print("SUMMARY")
for r in rows: print(r,flush=True)
Path("fasti_results.json").write_text(json.dumps(rows,indent=2))
