from pathlib import Path
import subprocess,json,collections

ROOT=Path("silesia"); OUT=Path("exp45_out"); OUT.mkdir(exist_ok=True)
FILES=["mozilla","mr","ooffice","sao","x-ray"]
CH=512*1024

def transpose(buf,w):
    rows=len(buf)//w; main=rows*w
    out=bytearray()
    for c in range(w): out.extend(buf[c:main:w])
    out.extend(buf[main:])
    return bytes(out)

def byte_delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b-buf[i-lag])&255
    return bytes(out)

def word_transform(buf,w,kind):
    main=(len(buf)//w)*w
    out=bytearray(len(buf))
    prev=0
    mask=(1<<(8*w))-1
    for i in range(0,main,w):
        v=int.from_bytes(buf[i:i+w],"little")
        if i==0: z=v
        elif kind=="delta": z=(v-prev)&mask
        else: z=v^prev
        out[i:i+w]=z.to_bytes(w,"little")
        prev=v
    out[main:]=buf[main:]
    return bytes(out)

TRANS=[
 ("BASE",lambda b:b),
 ("BD4T4",lambda b:transpose(byte_delta_lag(b,4),4)),
 ("WD2T2",lambda b:transpose(word_transform(b,2,"delta"),2)),
 ("WD4T4",lambda b:transpose(word_transform(b,4,"delta"),4)),
 ("WD8T8",lambda b:transpose(word_transform(b,8,"delta"),8)),
 ("WX2T2",lambda b:transpose(word_transform(b,2,"xor"),2)),
 ("WX4T4",lambda b:transpose(word_transform(b,4,"xor"),4)),
 ("WX8T8",lambda b:transpose(word_transform(b,8,"xor"),8)),
]

rows=[]
for fn in FILES:
    data=(ROOT/fn).read_bytes()
    for idx,start in enumerate(range(0,len(data),CH)):
        chunk=data[start:start+CH]
        cand=[]
        for tag,fun in TRANS:
            payload=fun(chunk)
            inp=OUT/f"{fn}_{idx}_{tag}.bin"; arc=OUT/f"{fn}_{idx}_{tag}.aur"
            inp.write_bytes(payload)
            subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cand.append((arc.stat().st_size+1,tag))
            inp.unlink(); arc.unlink()
        cand.sort()
        base=next(s for s,t in cand if t=="BASE")
        rows.append(dict(file=fn,chunk=idx,raw=len(chunk),base=base,best_size=cand[0][0],best_mode=cand[0][1],saved=base-cand[0][0]))
        print(rows[-1],flush=True)

summary={}
for fn in FILES:
    rr=[r for r in rows if r["file"]==fn]
    raw=sum(r["raw"] for r in rr); base=sum(r["base"] for r in rr); best=sum(r["best_size"] for r in rr)
    summary[fn]=dict(raw=raw,base=base,best=best,saved=base-best,ratio=best/raw,
                     modes=dict(collections.Counter(r["best_mode"] for r in rr)))
tb=sum(r["base"] for r in rows); tt=sum(r["best_size"] for r in rows); tr=sum(r["raw"] for r in rows)
out=dict(total_raw=tr,total_base=tb,total_best=tt,total_saved=tb-tt,ratio=tt/tr,by_file=summary)
print("SUMMARY",json.dumps(out,indent=2),flush=True)
Path("exp45_results.json").write_text(json.dumps({"summary":out,"rows":rows},indent=2))
