from pathlib import Path
import subprocess,time,json,hashlib,shutil
ROOT=Path("silesia"); OUT=Path("fasth_ab"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
rows=[]
for tag,exe in [("FAST_D","./fast_d"),("FAST_H","./fast_h")]:
    rawtot=sizetot=0;ct=dt=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"{tag}_{fn}.aur"; dec=OUT/f"d_{tag}_{fn}"
        t=time.perf_counter()
        subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct+=time.perf_counter()-t
        if dec.exists(): shutil.rmtree(dec)
        t=time.perf_counter()
        subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt+=time.perf_counter()-t
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("SHA FAIL")
        rawtot+=raw;sizetot+=arc.stat().st_size
    rows.append(dict(profile=tag,size=sizetot,ratio=100*sizetot/rawtot,
                     comp_MBps=(rawtot/1e6)/ct,dec_MBps=(rawtot/1e6)/dt,sha=True))
print("SUMMARY")
for r in rows: print(r,flush=True)
Path("fasth_ab.json").write_text(json.dumps(rows,indent=2))
