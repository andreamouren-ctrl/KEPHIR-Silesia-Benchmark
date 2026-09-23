from pathlib import Path
import subprocess,json,collections

ROOT=Path("silesia"); OUT=Path("exp42_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","ooffice","osdb","reymont","sao","webster","x-ray"]
LAGS=[1,4,16,64,256,1024]
CH=512*1024

def delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b-buf[i-lag])&255
    return bytes(out)

rows=[]
for fn in FILES:
    data=(ROOT/fn).read_bytes()
    for idx,start in enumerate(range(0,len(data),CH)):
        chunk=data[start:start+CH]
        candidates=[]
        inp=OUT/f"{fn}_{idx}_base.bin"; arc=OUT/f"{fn}_{idx}_base.aur"
        inp.write_bytes(chunk)
        subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        candidates.append((arc.stat().st_size+1,"BASE",0))
        inp.unlink(); arc.unlink()
        for lag in LAGS:
            payload=delta_lag(chunk,lag)
            inp=OUT/f"{fn}_{idx}_d{lag}.bin"; arc=OUT/f"{fn}_{idx}_d{lag}.aur"
            inp.write_bytes(payload)
            subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            candidates.append((arc.stat().st_size+1,f"D{lag}",lag))
            inp.unlink(); arc.unlink()
        candidates.sort()
        best=candidates[0]
        base=next(x[0] for x in candidates if x[1]=="BASE")
        rows.append(dict(file=fn,chunk=idx,raw=len(chunk),base=base,best_size=best[0],best_mode=best[1],saved=base-best[0]))

summary={}
for fn in FILES:
    rr=[r for r in rows if r["file"]==fn]
    base=sum(r["base"] for r in rr); best=sum(r["best_size"] for r in rr); raw=sum(r["raw"] for r in rr)
    summary[fn]=dict(raw=raw,base=base,best=best,saved=base-best,ratio=best/raw,
                     modes=dict(collections.Counter(r["best_mode"] for r in rr)))
total_base=sum(r["base"] for r in rows); total_best=sum(r["best_size"] for r in rows); total_raw=sum(r["raw"] for r in rows)
out=dict(total_raw=total_raw,total_base=total_base,total_best=total_best,total_saved=total_base-total_best,
         ratio=total_best/total_raw,by_file=summary)
print("SUMMARY",json.dumps(out,indent=2),flush=True)
Path("exp42_results.json").write_text(json.dumps({"summary":out,"rows":rows},indent=2))
