from pathlib import Path
import subprocess,math,json,collections,statistics,shutil,hashlib

ROOT=Path("silesia"); OUT=Path("exp40_chunks"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
CH=512*1024

def entropy(buf):
    if not buf: return 0.0
    cnt=collections.Counter(buf); n=len(buf)
    return -sum((c/n)*math.log2(c/n) for c in cnt.values())

def eqrate(buf,lag):
    if len(buf)<=lag: return 0.0
    m=sum(1 for i in range(lag,len(buf)) if buf[i]==buf[i-lag])
    return m/(len(buf)-lag)

def residuals(buf):
    # Cheap geometry-aware predictor aligned with KEPHIR's 1/16/256 neighborhood.
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        vals=[]
        if i>=1: vals.append((buf[i-1],3))
        if i>=16: vals.append((buf[i-16],2))
        if i>=256: vals.append((buf[i-256],2))
        if i>=17: vals.append((buf[i-17],1))
        if i>=15: vals.append((buf[i-15],1))
        if vals:
            num=sum(v*w for v,w in vals); den=sum(w for _,w in vals)
            p=(num+den//2)//den
        else: p=0
        out[i]=(b-p)&255
    return out

rows=[]
for fn in FILES:
    data=(ROOT/fn).read_bytes()
    for idx,start in enumerate(range(0,len(data),CH)):
        chunk=data[start:start+CH]
        cp=OUT/f"{fn}_{idx:04d}.bin"; arc=OUT/f"{fn}_{idx:04d}.aur"; dec=OUT/f"dec_{fn}_{idx:04d}"
        cp.write_bytes(chunk)
        subprocess.run(["./kephir37","cp",str(cp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        raw=len(chunk); size=arc.stat().st_size
        rbuf=residuals(chunk)
        printable=sum(1 for c in chunk if (32<=c<=126) or c in (9,10,13))/raw
        target=0.26*raw
        excess=max(0,size-target)
        rows.append(dict(file=fn,chunk=idx,raw=raw,size=size,ratio=size/raw,
                         byte_entropy=entropy(chunk),res_entropy=entropy(rbuf),
                         printable=printable,eq1=eqrate(chunk,1),eq16=eqrate(chunk,16),eq256=eqrate(chunk,256),
                         excess_vs_26=excess))
        cp.unlink(); arc.unlink()

# rule-based diagnostic classes
for r in rows:
    if r["ratio"]<=0.26: cls="already_at_or_below_26"
    elif r["res_entropy"]<=5.2 and (r["eq16"]>0.10 or r["eq256"]>0.08): cls="structured_residual"
    elif r["byte_entropy"]>=7.4 and r["res_entropy"]>=7.1: cls="high_entropy_hard"
    elif r["printable"]>=0.75: cls="textual"
    elif r["eq1"]>0.12 or r["eq16"]>0.08 or r["eq256"]>0.06: cls="repeat_structured"
    else: cls="mixed"
    r["class"]=cls

agg={}
for cls in sorted(set(r["class"] for r in rows)):
    rr=[r for r in rows if r["class"]==cls]
    raw=sum(r["raw"] for r in rr); size=sum(r["size"] for r in rr); excess=sum(r["excess_vs_26"] for r in rr)
    agg[cls]=dict(chunks=len(rr),raw=raw,size=size,ratio=size/raw,excess_vs_26=excess,
                  share_of_total_excess=0.0,
                  avg_byte_entropy=statistics.mean(r["byte_entropy"] for r in rr),
                  avg_res_entropy=statistics.mean(r["res_entropy"] for r in rr),
                  avg_eq16=statistics.mean(r["eq16"] for r in rr),
                  avg_eq256=statistics.mean(r["eq256"] for r in rr))
tot_excess=sum(r["excess_vs_26"] for r in rows)
for v in agg.values(): v["share_of_total_excess"]=v["excess_vs_26"]/tot_excess if tot_excess else 0

worst=sorted(rows,key=lambda r:r["excess_vs_26"],reverse=True)[:30]
summary=dict(total_raw=sum(r["raw"] for r in rows),total_size=sum(r["size"] for r in rows),
             overall_ratio=sum(r["size"] for r in rows)/sum(r["raw"] for r in rows),
             target_26_size=0.26*sum(r["raw"] for r in rows),
             total_excess_vs_26=tot_excess,classes=agg,worst_chunks=worst)
Path("exp40_diagnostic.json").write_text(json.dumps(dict(summary=summary,rows=rows),indent=2))
print("SUMMARY",json.dumps(summary,indent=2))
