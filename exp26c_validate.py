from pathlib import Path
import subprocess,time,statistics,hashlib,json,shutil
ROOT=Path("silesia"); OUT=Path("exp26c_validate"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
rows=[]
for name in FILES:
    p=ROOT/name; raw=p.stat().st_size; arc=OUT/f"{name}.aur"
    ctimes=[]
    for _ in range(3):
        if arc.exists(): arc.unlink()
        t=time.perf_counter()
        subprocess.run(["./kephir26_9","cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ctimes.append(time.perf_counter()-t)
    size=arc.stat().st_size
    dec=OUT/f"dec_{name}"; dtimes=[]
    for _ in range(3):
        if dec.exists(): shutil.rmtree(dec)
        t=time.perf_counter()
        subprocess.run(["./kephir26_9","dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dtimes.append(time.perf_counter()-t)
    ok=hashlib.sha256((dec/name).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
    if not ok: raise SystemExit(f"SHA FAIL {name}")
    rows.append(dict(file=name,raw=raw,size=size,ratio=100*size/raw,
                     comp_MBps=raw/1e6/statistics.median(ctimes),
                     dec_MBps=raw/1e6/statistics.median(dtimes),sha_ok=ok))
raw=sum(r["raw"] for r in rows); size=sum(r["size"] for r in rows)
ct=sum(r["raw"]/1e6/r["comp_MBps"] for r in rows)
dt=sum(r["raw"]/1e6/r["dec_MBps"] for r in rows)
summary=dict(profile="KEPHIR EXP-26C BAND-TUNED",raw=raw,size=size,ratio=100*size/raw,
             comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,sha_all=True,
             params={"LIT":6.55,"MC":9.42,"DPEN_BASE":1.20,
                     "text_ge_0_75":1.02,"text_le_0_35":0.95,"otherwise":1.15})
print("SUMMARY",summary,flush=True)
for r in rows: print(r,flush=True)
Path("exp26c_validation.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
