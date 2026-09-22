from pathlib import Path
import subprocess, json, hashlib, time

ROOT=Path("silesia")
OUT=Path("exp23_out"); OUT.mkdir(exist_ok=True)
FILES=["x-ray","dickens","webster","sao","nci","xml","reymont","mozilla"]
PROFILES=[
 ("BASE",6.48,9.42,1.88),
 ("A_AGGR",6.60,9.20,1.80),
 ("B_DIST",6.55,9.42,1.70),
 ("C_BAL",6.55,9.25,1.78),
]
rows=[]
for tag,lit,mc,dpen in PROFILES:
    total_raw=total_size=0
    print("\nPROFILE",tag,lit,mc,dpen,flush=True)
    for name in FILES:
        p=ROOT/name; out=OUT/f"{tag}_{name}.aur"
        t=time.perf_counter()
        subprocess.run(["./kephir22","cp",str(p),str(out),"6",str(lit),str(mc),str(dpen)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        sec=time.perf_counter()-t
        raw=p.stat().st_size; size=out.stat().st_size
        total_raw+=raw; total_size+=size
        rows.append(dict(profile=tag,file=name,raw=raw,size=size,ratio=100*size/raw,seconds=sec,
                         LIT=lit,MC=mc,DPEN=dpen))
        print(f"{tag:8s} {name:8s} {size:10d} {100*size/raw:8.4f}% {sec:7.3f}s",flush=True)
    print(f"TOTAL {tag} {total_size} {100*total_size/total_raw:.6f}%",flush=True)
Path("exp23_sweep.json").write_text(json.dumps(rows,indent=2))

base={(r["file"]):r for r in rows if r["profile"]=="BASE"}
summary=[]
for tag,lit,mc,dpen in PROFILES:
    rr=[r for r in rows if r["profile"]==tag]
    raw=sum(r["raw"] for r in rr); size=sum(r["size"] for r in rr)
    delta=sum(r["size"]-base[r["file"]]["size"] for r in rr)
    guards=sum(r["size"]-base[r["file"]]["size"] for r in rr if r["file"] in ["nci","xml","reymont","mozilla"])
    weak=sum(r["size"]-base[r["file"]]["size"] for r in rr if r["file"] in ["x-ray","dickens","webster","sao"])
    summary.append(dict(profile=tag,LIT=lit,MC=mc,DPEN=dpen,size=size,ratio=100*size/raw,
                        delta_vs_base=delta,weak_delta=weak,guard_delta=guards))
Path("exp23_summary.json").write_text(json.dumps(summary,indent=2))
print("\nSUMMARY")
for r in sorted(summary,key=lambda x:x["size"]):
    print(r,flush=True)
