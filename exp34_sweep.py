from pathlib import Path
import subprocess,time,json,hashlib,shutil
ROOT=Path("silesia"); OUT=Path("exp34_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
MODES=[("EXP33H_BASE",0),("EXP34A_ANCHORS",1),("EXP34B_QUOTIENT",2),("EXP34C_COMBINED",3)]
rows=[]
for tag,mode in MODES:
    exe=f"./kephir34_{mode}"
    print("\nMODE",tag,flush=True)
    for name in FILES:
        p=ROOT/name; arc=OUT/f"{tag}_{name}.aur"
        t=time.perf_counter()
        subprocess.run([exe,"cp",str(p),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        sec=time.perf_counter()-t
        raw=p.stat().st_size; size=arc.stat().st_size
        dec=OUT/f"dec_{tag}_{name}"
        if dec.exists(): shutil.rmtree(dec)
        subprocess.run([exe,"dp",str(arc),str(dec),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ok=hashlib.sha256((dec/name).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit(f"SHA FAIL {tag} {name}")
        rows.append(dict(mode=tag,file=name,raw=raw,size=size,seconds=sec,sha_ok=ok))
        print(rows[-1],flush=True)
summary=[]
for tag,mode in MODES:
    rr=[r for r in rows if r["mode"]==tag]
    raw=sum(r["raw"] for r in rr); size=sum(r["size"] for r in rr); sec=sum(r["seconds"] for r in rr)
    summary.append(dict(mode=tag,size=size,ratio=100*size/raw,comp_MBps=(raw/1e6)/sec,sha_all=True))
summary.sort(key=lambda x:x["size"])
print("\nSUMMARY")
for r in summary: print(r,flush=True)
Path("exp34_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
