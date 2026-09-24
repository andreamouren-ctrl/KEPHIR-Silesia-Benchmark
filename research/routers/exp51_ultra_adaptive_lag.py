from pathlib import Path
import subprocess,struct,hashlib,time,json,shutil,collections

MAGIC=b"K51U"
CH=512*1024
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]

# EXP-48 fixed transforms plus additional reversible lag surfaces.
# The extra lags are intentionally limited to powers-of-two / nearby structural periods
# already motivated by EXP-42/47. ULTRA prioritizes final size over encode cost.
EXTRA_LAGS=[1,3,8,32,64,128,256,512,2048,4096]
MODE_TO_LAG={6+i:lag for i,lag in enumerate(EXTRA_LAGS)}
LAG_TO_MODE={lag:mode for mode,lag in MODE_TO_LAG.items()}

def delta_lag(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b-buf[i-lag])&255
    return bytes(out)

def inv_delta(buf,lag):
    out=bytearray(len(buf))
    for i,b in enumerate(buf):
        out[i]=b if i<lag else (b+out[i-lag])&255
    return bytes(out)

def transpose(buf,w):
    rows=len(buf)//w; main=rows*w
    out=bytearray()
    for c in range(w): out.extend(buf[c:main:w])
    out.extend(buf[main:])
    return bytes(out)

def inv_transpose(buf,w,rawlen):
    rows=rawlen//w; main=rows*w
    out=bytearray(rawlen); k=0
    for c in range(w):
        for r in range(rows):
            out[r*w+c]=buf[k]; k+=1
    out[main:]=buf[k:]
    return bytes(out)

def word_xor(buf,w):
    main=(len(buf)//w)*w
    out=bytearray(len(buf)); prev=0
    for i in range(0,main,w):
        v=int.from_bytes(buf[i:i+w],"little")
        z=v if i==0 else v^prev
        out[i:i+w]=z.to_bytes(w,"little")
        prev=v
    out[main:]=buf[main:]
    return bytes(out)

def inv_word_xor(buf,w):
    main=(len(buf)//w)*w
    out=bytearray(len(buf)); prev=0
    for i in range(0,main,w):
        z=int.from_bytes(buf[i:i+w],"little")
        v=z if i==0 else z^prev
        out[i:i+w]=v.to_bytes(w,"little")
        prev=v
    out[main:]=buf[main:]
    return bytes(out)

def transform(buf,mode):
    if mode==0:return buf
    if mode==1:return transpose(delta_lag(buf,4),4)
    if mode==2:return transpose(delta_lag(buf,1024),1024)
    if mode==3:return transpose(word_xor(buf,2),2)
    if mode==4:return transpose(delta_lag(buf,2),2)
    if mode==5:return transpose(delta_lag(buf,16),16)
    if mode in MODE_TO_LAG:
        lag=MODE_TO_LAG[mode]
        return transpose(delta_lag(buf,lag),lag)
    raise ValueError(mode)

def inverse(buf,mode,rawlen):
    if mode==0:return buf
    if mode==1:return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2:return inv_delta(inv_transpose(buf,1024,rawlen),1024)
    if mode==3:return inv_word_xor(inv_transpose(buf,2,rawlen),2)
    if mode==4:return inv_delta(inv_transpose(buf,2,rawlen),2)
    if mode==5:return inv_delta(inv_transpose(buf,16,rawlen),16)
    if mode in MODE_TO_LAG:
        lag=MODE_TO_LAG[mode]
        return inv_delta(inv_transpose(buf,lag,rawlen),lag)
    raise ValueError(mode)

def kephir_cp(payload,tmpbase):
    inp=tmpbase.with_suffix(".bin"); arc=tmpbase.with_suffix(".aur")
    inp.write_bytes(payload)
    subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data=arc.read_bytes()
    inp.unlink();arc.unlink()
    return data

def kephir_dp(payload,tmpbase):
    arc=tmpbase.with_suffix(".aur"); outdir=tmpbase.parent/(tmpbase.name+"_d")
    arc.write_bytes(payload)
    if outdir.exists():shutil.rmtree(outdir)
    subprocess.run(["./kephir37","dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    assert len(files)==1
    data=files[0].read_bytes()
    arc.unlink();shutil.rmtree(outdir)
    return data

def encode(src,dst,tmp):
    raw=src.read_bytes(); entries=[]; chosen=collections.Counter()
    modes=list(range(0,6))+sorted(MODE_TO_LAG)
    for idx,start in enumerate(range(0,len(raw),CH)):
        chunk=raw[start:start+CH]
        candidates=[]
        for mode in modes:
            payload=transform(chunk,mode)
            comp=kephir_cp(payload,tmp/f"c_{idx}_{mode}")
            candidates.append((len(comp),mode,comp))
        _,mode,comp=min(candidates,key=lambda x:x[0])
        chosen[mode]+=1
        entries.append((mode,len(chunk),comp))
    with dst.open("wb") as f:
        f.write(MAGIC);f.write(struct.pack("<QI",len(raw),len(entries)))
        for mode,n,comp in entries:
            f.write(struct.pack("<BII",mode,n,len(comp)));f.write(comp)
    return chosen

def decode(src,dst,tmp):
    b=src.read_bytes();pos=0
    assert b[:4]==MAGIC;pos=4
    total,count=struct.unpack_from("<QI",b,pos);pos+=12
    out=bytearray()
    for idx in range(count):
        mode,n,cs=struct.unpack_from("<BII",b,pos);pos+=9
        comp=b[pos:pos+cs];pos+=cs
        transformed=kephir_dp(comp,tmp/f"d_{idx}")
        raw=inverse(transformed,mode,n)
        assert len(raw)==n
        out.extend(raw)
    assert len(out)==total
    dst.write_bytes(out)

root=Path("silesia");out=Path("exp51_out");tmp=out/"tmp"
out.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
rows=[]
for fn in FILES:
    src=root/fn;arc=out/f"{fn}.k51";dec=out/f"{fn}.dec"
    t=time.perf_counter();chosen=encode(src,arc,tmp);ct=time.perf_counter()-t
    t=time.perf_counter();decode(arc,dec,tmp);dt=time.perf_counter()-t
    ok=hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dec.read_bytes()).digest()
    if not ok:raise SystemExit("SHA FAIL "+fn)
    raw=src.stat().st_size;size=arc.stat().st_size
    labels={}
    for m,c in sorted(chosen.items()):
        if m==0:name="BASE"
        elif m==1:name="D4T4"
        elif m==2:name="D1024T1024"
        elif m==3:name="XOR2T2"
        elif m==4:name="D2T2"
        elif m==5:name="D16T16"
        else:
            lag=MODE_TO_LAG[m];name=f"D{lag}T{lag}"
        labels[name]=c
    row=dict(file=fn,raw=raw,size=size,ratio=size/raw,
             comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt,modes=labels,sha_ok=ok)
    rows.append(row);print(row,flush=True)
    dec.unlink()

raw=sum(r["raw"] for r in rows);size=sum(r["size"] for r in rows)
ct=sum(r["raw"]/1e6/r["comp_MBps"] for r in rows)
dt=sum(r["raw"]/1e6/r["dec_MBps"] for r in rows)
summary=dict(
 raw=raw,size=size,ratio=size/raw,
 comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,
 sha_all=all(r["sha_ok"] for r in rows),
 baseline_exp48_size=63201140,
 delta_bytes=size-63201140,
 improvement_bytes=63201140-size,
 improvement_pct=(63201140-size)/63201140*100.0
)
print("SUMMARY",json.dumps(summary,indent=2),flush=True)
Path("exp51_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
