from pathlib import Path
import subprocess,struct,hashlib,time,json,shutil,collections

MAGIC=b"K56U"
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
    raise ValueError(mode)

def inverse(buf,mode,rawlen):
    if mode==0:return buf
    if mode==1:return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2:return inv_delta(inv_transpose(buf,1024,rawlen),1024)
    if mode==3:return inv_word_xor(inv_transpose(buf,2,rawlen),2)
    if mode==4:return inv_delta(inv_transpose(buf,2,rawlen),2)
    if mode==5:return inv_delta(inv_transpose(buf,16,rawlen),16)
    raise ValueError(mode)

def cp(exe,payload,tmpbase):
    inp=tmpbase.with_suffix(".bin"); arc=tmpbase.with_suffix(".aur")
    inp.write_bytes(payload)
    subprocess.run([exe,"cp",str(inp),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data=arc.read_bytes()
    inp.unlink();arc.unlink()
    return data

def dp(exe,payload,tmpbase):
    arc=tmpbase.with_suffix(".aur"); outdir=tmpbase.parent/(tmpbase.name+"_d")
    arc.write_bytes(payload)
    if outdir.exists():shutil.rmtree(outdir)
    subprocess.run([exe,"dp",str(arc),str(outdir),"6"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    files=[p for p in outdir.rglob("*") if p.is_file()]
    assert len(files)==1
    data=files[0].read_bytes()
    arc.unlink();shutil.rmtree(outdir)
    return data

def best_leaf(chunk,tmpbase,tag):
    candidates=[]
    for mode in range(6):
        payload=transform(chunk,mode)
        for backend,exe in ((0,"./kephir37"),(1,"./kephir53"),(2,"./kephir55")):
            comp=cp(exe,payload,tmpbase/f"{tag}_{mode}_{backend}")
            candidates.append((len(comp),backend,mode,comp))
    _,backend,mode,comp=min(candidates,key=lambda x:x[0])
    return backend,mode,comp

def encode(src,dst,tmp):
    raw=src.read_bytes(); entries=[]; chosen=collections.Counter(); grains=collections.Counter()
    for pidx,start in enumerate(range(0,len(raw),CH)):
        parent=raw[start:start+CH]

        # Candidate A: one 512 KiB (or tail) leaf.
        b,m,c=best_leaf(parent,tmp,f"p{pidx}_512")
        best_cost=9+len(c)
        best_entries=[(b,m,len(parent),c)]

        # Candidate B: split into up to two 256 KiB leaves.
        if len(parent)>256*1024:
            e256=[]; cost256=0
            for j,off in enumerate(range(0,len(parent),256*1024)):
                part=parent[off:off+256*1024]
                bb,mm,cc=best_leaf(part,tmp,f"p{pidx}_256_{j}")
                e256.append((bb,mm,len(part),cc)); cost256+=9+len(cc)
            if cost256<best_cost:
                best_cost=cost256;best_entries=e256

        # Candidate C: split into up to four 128 KiB leaves.
        if len(parent)>128*1024:
            e128=[]; cost128=0
            for j,off in enumerate(range(0,len(parent),128*1024)):
                part=parent[off:off+128*1024]
                bb,mm,cc=best_leaf(part,tmp,f"p{pidx}_128_{j}")
                e128.append((bb,mm,len(part),cc)); cost128+=9+len(cc)
            if cost128<best_cost:
                best_cost=cost128;best_entries=e128

        for backend,mode,n,comp in best_entries:
            chosen[(backend,mode)]+=1
            grains[n]+=1
            entries.append((backend,mode,n,comp))

    with dst.open("wb") as f:
        f.write(MAGIC);f.write(struct.pack("<QI",len(raw),len(entries)))
        for backend,mode,n,comp in entries:
            desc=mode + 6*backend
            f.write(struct.pack("<BII",desc,n,len(comp)));f.write(comp)
    return chosen,grains

def decode(src,dst,tmp):
    b=src.read_bytes();pos=0
    assert b[:4]==MAGIC;pos=4
    total,count=struct.unpack_from("<QI",b,pos);pos+=12
    out=bytearray()
    for idx in range(count):
        desc,n,cs=struct.unpack_from("<BII",b,pos);pos+=9
        comp=b[pos:pos+cs];pos+=cs
        backend,mode=divmod(desc,6)
        exe=("./kephir37" if backend==0 else ("./kephir53" if backend==1 else "./kephir55"))
        transformed=dp(exe,comp,tmp/f"d_{idx}")
        raw=inverse(transformed,mode,n)
        assert len(raw)==n
        out.extend(raw)
    assert len(out)==total
    dst.write_bytes(out)

root=Path("silesia");out=Path("exp56_out");tmp=out/"tmp"
out.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
rows=[]
for fn in FILES:
    src=root/fn;arc=out/f"{fn}.k56";dec=out/f"{fn}.dec"
    t=time.perf_counter();chosen,grains=encode(src,arc,tmp);ct=time.perf_counter()-t
    t=time.perf_counter();decode(arc,dec,tmp);dt=time.perf_counter()-t
    ok=hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dec.read_bytes()).digest()
    if not ok: raise SystemExit("SHA FAIL "+fn)
    raw=src.stat().st_size;size=arc.stat().st_size
    labels={}
    for (backend,mode),count in sorted(chosen.items()):
        labels[f"{('EXP48' if backend==0 else ('EXP53' if backend==1 else 'EXP55'))}_M{mode}"]=count
    row=dict(file=fn,raw=raw,size=size,ratio=size/raw,
             comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt,modes=labels,grains={str(k):v for k,v in sorted(grains.items())},sha_ok=ok)
    rows.append(row);print(row,flush=True)
    dec.unlink()

raw=sum(r["raw"] for r in rows);size=sum(r["size"] for r in rows)
ct=sum(r["raw"]/1e6/r["comp_MBps"] for r in rows)
dt=sum(r["raw"]/1e6/r["dec_MBps"] for r in rows)
all_modes=collections.Counter()
for r in rows: all_modes.update(r["modes"])
summary=dict(
    raw=raw,size=size,ratio=size/raw,
    comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,
    sha_all=all(r["sha_ok"] for r in rows),
    modes=dict(all_modes),
    baseline_exp55_size=63200596,
    delta_bytes=size-63200596,
    improvement_bytes=63200596-size,
    improvement_pct=(63200596-size)/63200596*100.0
)
print("SUMMARY",json.dumps(summary,indent=2),flush=True)
Path("exp56_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
