from pathlib import Path
import subprocess,time,statistics,hashlib,json
ROOT=Path("silesia"); OUT=Path("exp23_full_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
LIT,MC,DPEN=6.55,9.42,1.20
rows=[]
for name in FILES:
    p=ROOT/name; raw=p.stat().st_size; arc=OUT/f"{name}.aur"
    ctimes=[]
    for _ in range(3):
        if arc.exists(): arc.unlink()
        t=time.perf_counter()
        subprocess.run(["./kephir22","cp",str(p),str(arc),"6",str(LIT),str(MC),str(DPEN)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ctimes.append(time.perf_counter()-t)
    size=arc.stat().st_size
    decroot=OUT/f"dec_{name}"
    dtimes=[]
    for _ in range(3):
        if decroot.exists():
            import shutil; shutil.rmtree(decroot)
        t=time.perf_counter()
        subprocess.run(["./kephir22","dp",str(arc),str(decroot),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dtimes.append(time.perf_counter()-t)
    restored=(decroot/name).read_bytes()
    ok=hashlib.sha256(restored).digest()==hashlib.sha256(p.read_bytes()).digest()
    if not ok: raise SystemExit(f"SHA FAIL {name}")
    row=dict(file=name,raw=raw,size=size,ratio=100*size/raw,
             comp_MBps=raw/1e6/statistics.median(ctimes),
             dec_MBps=raw/1e6/statistics.median(dtimes),sha_ok=ok)
    rows.append(row)
    print(row,flush=True)
raw=sum(r["raw"] for r in rows); size=sum(r["size"] for r in rows)
comp_t=sum(r["raw"]/1e6/r["comp_MBps"] for r in rows)
dec_t=sum(r["raw"]/1e6/r["dec_MBps"] for r in rows)
summary=dict(profile="KEPHIR EXP-23 DPEN120",LIT=LIT,MC=MC,DPEN=DPEN,raw=raw,size=size,
             ratio=100*size/raw,comp_MBps=(raw/1e6)/comp_t,dec_MBps=(raw/1e6)/dec_t,sha_all=True)
print("SUMMARY",summary,flush=True)
Path("exp23_full_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
