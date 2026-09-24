from pathlib import Path
import subprocess,struct,hashlib,time,json,shutil

MAGIC=b"K44R"
CH=512*1024
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]

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

def inv_transpose(buf,w,rawlen):
    rows=rawlen//w; main=rows*w
    out=bytearray(rawlen); k=0
    for c in range(w):
        n=rows
        for r in range(n):
            out[r*w+c]=buf[k]; k+=1
    out[main:]=buf[k:]
    return bytes(out)

def transform(buf,mode):
    if mode==0:return buf
    if mode==1:return transpose(delta_lag(buf,4),4)
    if mode==2:return transpose(delta_lag(buf,1024),1024)
    if mode==3:return transpose(word_xor(buf,2),2)
    raise ValueError

def inverse(buf,mode,rawlen):
    if mode==0:return buf
    if mode==1:return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2:return inv_delta(inv_transpose(buf,1024,rawlen),1024)
    if mode==3:return inv_word_xor(inv_transpose(buf,2,rawlen),2)
    raise ValueError

def kephir_cp(payload,tmpbase):
    inp=tmpbase.with_suffix(".bin"); arc=tmpbase.with_suffix(".aur")
    inp.write_bytes(payload)
    subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data=arc.read_bytes()
    inp.unlink(); arc.unlink()
    return data

def kephir_dp(payload,tmpbase):
    arc=tmpbase.with_suffix(".aur"); outdir=tmpbase.parent/(tmpbase.name+"_d")
    arc.write_bytes(payload)
    if outdir.exists():shutil.rmtree(outdir)
    subprocess.run(["./kephir37","dp",str(arc),str(outdir),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    assert len(files)==1
    data=files[0].read_bytes()
    arc.unlink(); shutil.rmtree(outdir)
    return data

def encode(src,dst,tmp):
    raw=src.read_bytes(); entries=[]; chosen={0:0,1:0,2:0,3:0}
    for idx,start in enumerate(range(0,len(raw),CH)):
        chunk=raw[start:start+CH]
        candidates=[]
        for mode in (0,1,2,3):
            p=transform(chunk,mode)
            comp=kephir_cp(p,tmp/f"c_{idx}_{mode}")
            candidates.append((len(comp),mode,comp))
        _,mode,comp=min(candidates,key=lambda x:x[0])
        chosen[mode]+=1
        entries.append((mode,len(chunk),comp))
    with dst.open("wb") as f:
        f.write(MAGIC); f.write(struct.pack("<QI",len(raw),len(entries)))
        for mode,n,comp in entries:
            f.write(struct.pack("<BII",mode,n,len(comp))); f.write(comp)
    return chosen

def decode(src,dst,tmp):
    b=src.read_bytes(); pos=0
    assert b[:4]==MAGIC; pos=4
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

root=Path("silesia"); out=Path("exp44_out"); tmp=out/"tmp"; out.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
rows=[]
for fn in FILES:
    src=root/fn; arc=out/f"{fn}.k44"; dec=out/f"{fn}.dec"
    t=time.perf_counter(); chosen=encode(src,arc,tmp); ct=time.perf_counter()-t
    t=time.perf_counter(); decode(arc,dec,tmp); dt=time.perf_counter()-t
    ok=hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dec.read_bytes()).digest()
    if not ok: raise SystemExit("SHA FAIL "+fn)
    raw=src.stat().st_size; size=arc.stat().st_size
    rows.append(dict(file=fn,raw=raw,size=size,ratio=size/raw,comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt,modes=chosen,sha_ok=ok))
    dec.unlink()
    print(rows[-1],flush=True)

raw=sum(r["raw"] for r in rows);size=sum(r["size"] for r in rows)
ct=sum(r["raw"]/1e6/r["comp_MBps"] for r in rows);dt=sum(r["raw"]/1e6/r["dec_MBps"] for r in rows)
summary=dict(raw=raw,size=size,ratio=size/raw,comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,
             sha_all=all(r["sha_ok"] for r in rows),
             modes={str(m):sum(r["modes"][m] for r in rows) for m in (0,1,2,3)})
print("SUMMARY",json.dumps(summary,indent=2),flush=True)
Path("exp44_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
