from pathlib import Path
import subprocess,json,hashlib,shutil,collections,math

ROOT=Path("silesia"); OUT=Path("exp41_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
CH=512*1024

def delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        if i<lag: out[i]=b
        else: out[i]=(b-buf[i-lag])&255
    return bytes(out)

def inv_delta(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        if i<lag: out[i]=b
        else: out[i]=(b+out[i-lag])&255
    return bytes(out)

rows=[]
for fn in FILES:
    data=(ROOT/fn).read_bytes()
    for idx,start in enumerate(range(0,len(data),CH)):
        chunk=data[start:start+CH]
        reps=[("BASE",chunk,0),("D16",delta_lag(chunk,16),1),("D256",delta_lag(chunk,256),2)]
        cand=[]
        for tag,payload,mode in reps:
            inp=OUT/f"{fn}_{idx}_{tag}.bin"; arc=OUT/f"{fn}_{idx}_{tag}.aur"
            inp.write_bytes(payload)
            subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            # account for 2-bit mode in future format conservatively as one byte per chunk
            size=arc.stat().st_size + 1
            cand.append((size,tag,mode,payload))
            inp.unlink(); arc.unlink()
        cand.sort(key=lambda x:x[0])
        best=cand[0]
        # verify transform reversibility
        if best[1]=="D16": assert inv_delta(best[3],16)==chunk
        if best[1]=="D256": assert inv_delta(best[3],256)==chunk
        rows.append(dict(file=fn,chunk=idx,raw=len(chunk),
                         base_size=next(x[0] for x in cand if x[1]=="BASE"),
                         d16_size=next(x[0] for x in cand if x[1]=="D16"),
                         d256_size=next(x[0] for x in cand if x[1]=="D256"),
                         best_mode=best[1],best_size=best[0]))

total_raw=sum(r["raw"] for r in rows)
base=sum(r["base_size"] for r in rows)
oracle=sum(r["best_size"] for r in rows)
counts=collections.Counter(r["best_mode"] for r in rows)
saved=base-oracle
byfile={}
for fn in FILES:
    rr=[r for r in rows if r["file"]==fn]
    br=sum(r["base_size"] for r in rr); orr=sum(r["best_size"] for r in rr)
    byfile[fn]=dict(base=br,oracle=orr,saved=br-orr,ratio=orr/sum(r["raw"] for r in rr),
                    modes=dict(collections.Counter(r["best_mode"] for r in rr)))
summary=dict(total_raw=total_raw,base_chunked=base,base_ratio=base/total_raw,
             oracle_size=oracle,oracle_ratio=oracle/total_raw,saved=saved,
             mode_counts=dict(counts),by_file=byfile)
print("SUMMARY",json.dumps(summary,indent=2),flush=True)
Path("exp41_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
