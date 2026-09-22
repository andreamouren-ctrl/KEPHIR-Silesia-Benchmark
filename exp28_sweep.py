from pathlib import Path
import subprocess,time,json,hashlib,shutil
ROOT=Path("silesia"); OUT=Path("exp28_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
MODES=[("EXP27A",0),("EXP28A_LEN_TO_DIST",1),("EXP28B_DIST_TO_LEN",2),("EXP28C_COUPLED",3)]
rows=[]
for tag,mode in MODES:
    exe=f"./kephir28_{mode}"
    total_raw=total_size=0
    print("\nMODE",tag,flush=True)
    for name in FILES:
        p=ROOT/name; arc=OUT/f"{tag}_{name}.aur"
        t=time.perf_counter()
        subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        sec=time.perf_counter()-t
        raw=p.stat().st_size; size=arc.stat().st_size
        total_raw+=raw; total_size+=size
        dec=OUT/f"dec_{tag}_{name}"
        if dec.exists(): shutil.rmtree(dec)
        subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ok=hashlib.sha256((dec/name).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit(f"SHA FAIL {tag} {name}")
        r=dict(mode=tag,file=name,raw=raw,size=size,ratio=100*size/raw,seconds=sec,sha_ok=ok)
        rows.append(r); print(r,flush=True)
    print("TOTAL",tag,total_size,100*total_size/total_raw,flush=True)
summary=[]
for tag,mode in MODES:
    rr=[r for r in rows if r["mode"]==tag]
    raw=sum(r["raw"] for r in rr); size=sum(r["size"] for r in rr); sec=sum(r["seconds"] for r in rr)
    summary.append(dict(mode=tag,size=size,ratio=100*size/raw,comp_MBps=(raw/1e6)/sec,sha_all=all(r["sha_ok"] for r in rr)))
summary.sort(key=lambda x:x["size"])
print("\nSUMMARY")
for r in summary: print(r,flush=True)
Path("exp28_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
