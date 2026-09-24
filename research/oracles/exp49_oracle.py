from pathlib import Path
import subprocess,json,collections

ROOT=Path("silesia"); OUT=Path("exp49_out"); OUT.mkdir(exist_ok=True)
FILES=["mozilla","ooffice","sao","x-ray"]
CH=512*1024

def bitplanes(buf):
    n=len(buf); out=bytearray((n+7)//8*8)
    k=0
    for bit in range(8):
        acc=0; cnt=0
        for b in buf:
            acc |= ((b>>bit)&1)<<cnt
            cnt+=1
            if cnt==8:
                out[k]=acc;k+=1;acc=0;cnt=0
        if cnt:
            out[k]=acc;k+=1
    return bytes(out[:k])

def nibbles(buf):
    # high-nibble stream followed by low-nibble stream, packed 2 per byte.
    hi=[b>>4 for b in buf]; lo=[b&15 for b in buf]
    out=bytearray((len(buf)+1)//2*2)
    k=0
    for arr in (hi,lo):
        for i in range(0,len(arr),2):
            a=arr[i]; b=arr[i+1] if i+1<len(arr) else 0
            out[k]=a|(b<<4);k+=1
    return bytes(out[:k])

def xorlag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else b^buf[i-lag]
    return bytes(out)

TRANS=[
 ("BASE",lambda b:b),
 ("BIT",bitplanes),
 ("NIB",nibbles),
 ("X1BIT",lambda b:bitplanes(xorlag(b,1))),
 ("X2BIT",lambda b:bitplanes(xorlag(b,2))),
 ("X4BIT",lambda b:bitplanes(xorlag(b,4))),
 ("X8BIT",lambda b:bitplanes(xorlag(b,8))),
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
            inp.unlink();arc.unlink()
        cand.sort()
        base=next(s for s,t in cand if t=="BASE")
        rows.append(dict(file=fn,chunk=idx,raw=len(chunk),base=base,best_size=cand[0][0],best_mode=cand[0][1],saved=base-cand[0][0]))
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
Path("exp49_results.json").write_text(json.dumps({"summary":out,"rows":rows},indent=2))
