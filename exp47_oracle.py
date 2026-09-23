from pathlib import Path
import subprocess,json,collections

ROOT=Path("silesia"); OUT=Path("exp47_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
CH=512*1024
LAGS=[1,2,3,4,8,16,32,64,128,256,512,1024,2048,4096]

def score_lag(buf,lag):
    if len(buf)<=lag:return 0.0
    step=max(1,(len(buf)-lag)//8192)
    n=0;m=0
    for i in range(lag,len(buf),step):
        n+=1
        if buf[i]==buf[i-lag]:m+=1
    return m/n if n else 0.0

def delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b-buf[i-lag])&255
    return bytes(out)

def transpose(buf,w):
    rows=len(buf)//w; main=rows*w
    out=bytearray()
    for c in range(w): out.extend(buf[c:main:w])
    out.extend(buf[main:])
    return bytes(out)

rows=[]
for fn in FILES:
    data=(ROOT/fn).read_bytes()
    for idx,start in enumerate(range(0,len(data),CH)):
        chunk=data[start:start+CH]
        scores=sorted(((score_lag(chunk,l),l) for l in LAGS),reverse=True)
        top=[l for _,l in scores[:3]]
        candidates=[("BASE",chunk,0)]
        for lag in top:
            candidates.append((f"D{lag}T{lag}",transpose(delta_lag(chunk,lag),lag),lag))
        measured=[]
        for tag,payload,lag in candidates:
            inp=OUT/f"{fn}_{idx}_{tag}.bin"; arc=OUT/f"{fn}_{idx}_{tag}.aur"
            inp.write_bytes(payload)
            subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            measured.append((arc.stat().st_size+1,tag,lag))
            inp.unlink();arc.unlink()
        measured.sort()
        base=next(s for s,t,l in measured if t=="BASE")
        rows.append(dict(file=fn,chunk=idx,raw=len(chunk),base=base,best_size=measured[0][0],
                         best_mode=measured[0][1],best_lag=measured[0][2],saved=base-measured[0][0],
                         top_lags=top,top_scores=[scores[i][0] for i in range(3)]))
        print(rows[-1],flush=True)

summary={}
for fn in FILES:
    rr=[r for r in rows if r["file"]==fn]
    raw=sum(r["raw"] for r in rr);base=sum(r["base"] for r in rr);best=sum(r["best_size"] for r in rr)
    summary[fn]=dict(raw=raw,base=base,best=best,saved=base-best,ratio=best/raw,
      modes=dict(collections.Counter(r["best_mode"] for r in rr)))
tb=sum(r["base"] for r in rows);tt=sum(r["best_size"] for r in rows);tr=sum(r["raw"] for r in rows)
out=dict(total_raw=tr,total_base=tb,total_best=tt,total_saved=tb-tt,ratio=tt/tr,by_file=summary)
print("SUMMARY",json.dumps(out,indent=2),flush=True)
Path("exp47_results.json").write_text(json.dumps({"summary":out,"rows":rows},indent=2))
