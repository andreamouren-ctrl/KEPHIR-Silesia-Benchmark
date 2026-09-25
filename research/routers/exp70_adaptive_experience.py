from pathlib import Path
import subprocess,struct,hashlib,time,json,shutil,collections,math,concurrent.futures,os

MAGIC=b"K70U"
CH=512*1024
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
# EXP-59: reversible selective text token transform.
# Marker 0xFF followed by 0 escapes a literal 0xFF; 1..N selects a token.
TEXT_TOKENS=[
    b" the ",b" and ",b"ing",b"tion",b" of ",b" to ",b" in ",b" that ",
    b" is ",b" for ",b"ed ",b"er ",b"re ",b"en ",b"on ",b"at ",
    b"\\n",b"</",b"/>",b"http",b"www.",b'="',b"<!--",b"-->",
    b"data",b"this",b"with",b"from",b"have",b"not ",b" as ",b" by "
]
TEXT_TOKENS_SORTED=sorted(enumerate(TEXT_TOKENS,1),key=lambda kv:len(kv[1]),reverse=True)
TEXT_TOKEN_INDEX={}
for tid,tok in TEXT_TOKENS_SORTED:
    TEXT_TOKEN_INDEX.setdefault(tok[0],[]).append((tid,tok))

def is_text_like(buf):
    if not buf:return False
    sample=buf[::32]
    printable=sum(1 for b in sample if b in (9,10,13) or 32<=b<127)/len(sample)
    letters_space=sum(1 for b in sample if b==32 or 65<=b<=90 or 97<=b<=122)/len(sample)
    return printable>=0.88 and letters_space>=0.58

def text_tokenize(buf):
    # EXP-60 single conceptual change:
    # candidate tokens are indexed by their first byte, avoiding the
    # EXP-59 O(tokens) scan at every input position.
    out=bytearray();i=0;n=len(buf)
    while i<n:
        b=buf[i]
        matched=False
        for tid,tok in TEXT_TOKEN_INDEX.get(b,()):
            if buf.startswith(tok,i):
                out.extend((255,tid));i+=len(tok);matched=True;break
        if matched:continue
        if b==255:out.extend((255,0))
        else:out.append(b)
        i+=1
    return bytes(out)

def text_detokenize(buf):
    out=bytearray();i=0;n=len(buf)
    while i<n:
        b=buf[i];i+=1
        if b!=255:
            out.append(b);continue
        if i>=n:raise ValueError("truncated text token stream")
        tid=buf[i];i+=1
        if tid==0:out.append(255)
        elif 1<=tid<=len(TEXT_TOKENS):out.extend(TEXT_TOKENS[tid-1])
        else:raise ValueError("invalid text token id")
    return bytes(out)


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

def word_xor(buf,w=2):
    main=(len(buf)//w)*w
    out=bytearray(len(buf)); prev=0
    for i in range(0,main,w):
        v=int.from_bytes(buf[i:i+w],"little")
        z=v if i==0 else v^prev
        out[i:i+w]=z.to_bytes(w,"little")
        prev=v
    out[main:]=buf[main:]
    return bytes(out)

def inv_word_xor(buf,w=2):
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
    if mode==6:return text_tokenize(buf)
    raise ValueError(mode)

def inverse(buf,mode,rawlen):
    if mode==0:return buf
    if mode==1:return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2:return inv_delta(inv_transpose(buf,1024,rawlen),1024)
    if mode==3:return inv_word_xor(inv_transpose(buf,2,rawlen),2)
    if mode==4:return inv_delta(inv_transpose(buf,2,rawlen),2)
    if mode==5:return inv_delta(inv_transpose(buf,16,rawlen),16)
    if mode==6:return text_detokenize(buf)
    raise ValueError(mode)

def cp(payload,tmpbase):
    inp=tmpbase.with_suffix(".bin"); arc=tmpbase.with_suffix(".aur")
    inp.write_bytes(payload)
    subprocess.run(["./kephir37","cp",str(inp),str(arc),"6","6.55","9.42","1.20"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data=arc.read_bytes()
    inp.unlink();arc.unlink()
    return data

def dp(payload,tmpbase):
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

def entropy_values(vals):
    if not vals:return 0.0
    c=collections.Counter(vals);n=len(vals)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def sample_entropy(buf,step=32):
    return entropy_values(buf[::step])

def residual_entropy(buf,lag,step=32):
    if len(buf)<=lag:return 99.0
    vals=[(buf[i]-buf[i-lag])&255 for i in range(lag,len(buf),step)]
    return entropy_values(vals)

def choose_mode(buf):
    # Cheap sampled residual test: only use a structural transform if it
    # gives a clear entropy advantage. Otherwise remain BASE.
    raw_h=sample_entropy(buf)
    cand=[
        (raw_h,0),
        (residual_entropy(buf,2),4),
        (residual_entropy(buf,4),1),
        (residual_entropy(buf,16),5),
        (residual_entropy(buf,1024),2),
    ]
    h,mode=min(cand,key=lambda x:x[0])
    if mode!=0 and raw_h-h<0.10:
        return 0
    return mode

def choose_grain(parent):
    if len(parent)<=128*1024:return len(parent)
    qs=[]
    q=128*1024
    for off in range(0,len(parent),q):
        part=parent[off:off+q]
        qs.append(sample_entropy(part,step=32))
    spread=max(qs)-min(qs) if qs else 0.0
    # Only split when the parent is measurably heterogeneous.
    if len(parent)>256*1024 and spread>=0.75:
        return 128*1024
    if len(parent)>256*1024 and spread>=0.40:
        return 256*1024
    return len(parent)


def feature_bucket(buf):
    if not buf:return "empty"
    sample=buf[::64]
    h=entropy_values(sample)
    zero=sum(1 for b in sample if b==0)/len(sample)
    printable=sum(1 for b in sample if b in (9,10,13) or 32<=b<127)/len(sample)
    # coarse, general-purpose bucket: size, entropy, zero-density, printability
    sb=0 if len(buf)<=131072 else (1 if len(buf)<=262144 else 2)
    hb=min(7,int(h))
    zb=min(4,int(zero*10))
    pb=min(4,int(printable*5))
    return f"s{sb}:h{hb}:z{zb}:p{pb}"

def learner_should_probe(model,key):
    st=model.get(key,{"seen":0,"trials":0,"wins":0,"gain":0,"cost":0.0})
    # mandatory exploration, then exploit positive families with sparse refresh probes
    if st["trials"]<3:return True
    if st["gain"]>0:return True
    return (st["seen"] % 16)==0

def learner_update(model,key,gain,cost):
    st=model.setdefault(key,{"seen":0,"trials":0,"wins":0,"gain":0,"cost":0.0})
    st["trials"]+=1
    st["gain"]+=int(gain)
    st["cost"]+=float(cost)
    if gain>0:st["wins"]+=1

def process_parcel(args):
    parcel,tmpdir=args
    tmp=Path(tmpdir)
    out=[]
    for seq,pidx,j,chunk,probe,key in parcel:
        mode=choose_mode(chunk)
        payload=transform(chunk,mode)
        comp=cp(payload,tmp/f"p{pidx}_{j}_m{mode}")
        if mode!=0:
            base_comp=cp(chunk,tmp/f"p{pidx}_{j}_basecheck")
            if len(base_comp)<=len(comp):
                mode=0
                comp=base_comp
        gain=0; extra_cost=0.0; probed=False
        # EXP-70 learner action: only if the learner requests a probe and the
        # final baseline mode is BASE/non-text. BASE is always retained if better.
        if probe and mode==0 and not is_text_like(chunk):
            t0=time.perf_counter()
            wx=transform(chunk,3)
            wx_comp=cp(wx,tmp/f"p{pidx}_{j}_wx")
            extra_cost=time.perf_counter()-t0
            probed=True
            if len(wx_comp)<len(comp):
                gain=len(comp)-len(wx_comp)
                mode=3;comp=wx_comp
        if is_text_like(chunk):
            tok=text_tokenize(chunk)
            if len(tok)+16 < len(chunk)*0.99:
                tok_comp=cp(tok,tmp/f"p{pidx}_{j}_text")
                if len(tok_comp)<len(comp):
                    mode=6;comp=tok_comp
        out.append((seq,mode,len(chunk),comp,key,probed,gain,extra_cost))
    return out

def estimate_task_cost(chunk):
    # Cheap scheduler-only estimate. Text-like chunks are substantially more
    # expensive because they add tokenization plus a possible extra backend encode.
    # Size remains the primary cost term.
    return len(chunk) * (2.25 if is_text_like(chunk) else 1.0)

def encode(src,dst,tmp,model):
    raw=src.read_bytes();entries=[];chosen=collections.Counter();grains=collections.Counter()
    tasks=[];seq=0;planned=0
    for pidx,start in enumerate(range(0,len(raw),CH)):
        parent=raw[start:start+CH]
        grain=choose_grain(parent)
        for j,off in enumerate(range(0,len(parent),grain)):
            chunk=parent[off:off+grain]
            key=feature_bucket(chunk)
            st=model.setdefault(key,{"seen":0,"trials":0,"wins":0,"gain":0,"cost":0.0})
            st["seen"]+=1
            probe=learner_should_probe(model,key)
            planned+=int(probe)
            tasks.append((seq,pidx,j,chunk,probe,key))
            seq+=1

    requested=max(1,min(16,int(os.environ.get("KEPHIR_WORKERS","16"))))
    workers=max(1,min(requested,os.cpu_count() or 1,len(tasks)))
    target_parcels=max(workers,min(len(tasks),workers*3))
    bins=[[] for _ in range(target_parcels)]
    loads=[0.0]*target_parcels
    weighted=sorted(tasks,key=lambda t:estimate_task_cost(t[3]),reverse=True)
    for task in weighted:
        bi=min(range(target_parcels),key=lambda k:loads[k])
        bins[bi].append(task)
        loads[bi]+=estimate_task_cost(task[3])
    parcels=[p for p in bins if p]

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        parcel_results=list(ex.map(process_parcel,[(p,str(tmp)) for p in parcels],chunksize=1))

    flat=[entry for parcel in parcel_results for entry in parcel]
    flat.sort(key=lambda x:x[0])
    entries=[(mode,n,comp) for _,mode,n,comp,_,_,_,_ in flat]
    probes=wins=gain_bytes=0;probe_cost=0.0
    for _,_,_,_,key,probed,gain,extra_cost in flat:
        if probed:
            probes+=1;wins+=int(gain>0);gain_bytes+=gain;probe_cost+=extra_cost
            learner_update(model,key,gain,extra_cost)

    for mode,n,comp in entries:
        chosen[mode]+=1;grains[n]+=1
    with dst.open("wb") as f:
        f.write(MAGIC);f.write(struct.pack("<QI",len(raw),len(entries)))
        for mode,n,comp in entries:
            f.write(struct.pack("<BII",mode,n,len(comp)));f.write(comp)
    imbalance=(max(loads)/((sum(loads)/len(loads)) or 1.0)) if loads else 1.0
    return chosen,grains,workers,len(parcels),imbalance,planned,probes,wins,gain_bytes,probe_cost

def decode(src,dst,tmp):
    b=src.read_bytes();pos=0
    assert b[:4]==MAGIC;pos=4
    total,count=struct.unpack_from("<QI",b,pos);pos+=12
    out=bytearray()
    for idx in range(count):
        mode,n,cs=struct.unpack_from("<BII",b,pos);pos+=9
        comp=b[pos:pos+cs];pos+=cs
        transformed=dp(comp,tmp/f"d_{idx}")
        raw=inverse(transformed,mode,n)
        assert len(raw)==n
        out.extend(raw)
    assert len(out)==total
    dst.write_bytes(out)


CORPORA=[
    ("Silesia",Path("corpora/silesia")),
    ("Canterbury",Path("corpora/canterbury")),
    ("Calgary",Path("corpora/calgary")),
    ("Canterbury-Large",Path("corpora/large")),
    ("Artificial",Path("corpora/artificial")),
    ("enwik8",Path("corpora/enwik8")),
]
out=Path("exp70_out");tmp=out/"tmp";out.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
model={}
epochs=[]
for epoch in range(1,4):
    erows=[]
    for cname,croot in CORPORA:
        files=sorted([p for p in croot.rglob("*") if p.is_file()])
        for fi,src in enumerate(files):
            safe=f"{cname}_{fi}"
            arc=out/f"e{epoch}_{safe}.k70";dec=out/f"e{epoch}_{safe}.dec"
            t=time.perf_counter()
            chosen,grains,workers_used,parcel_count,imbalance,planned,probes,wins,gain_bytes,probe_cost=encode(src,arc,tmp,model)
            ct=time.perf_counter()-t
            t=time.perf_counter();decode(arc,dec,tmp);dt=time.perf_counter()-t
            ok=hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dec.read_bytes()).digest()
            if not ok:raise SystemExit("SHA FAIL "+str(src))
            raw=src.stat().st_size;size=arc.stat().st_size
            erows.append(dict(epoch=epoch,corpus=cname,file=str(src.relative_to(croot)),raw=raw,size=size,ratio=size/raw,
                              comp_time_s=ct,dec_time_s=dt,comp_MBps=raw/1e6/ct if ct else 0,
                              probes=probes,wins=wins,gain_bytes=gain_bytes,probe_cost_s=probe_cost,
                              model_buckets=len(model),sha_ok=ok))
            dec.unlink()
    raw=sum(r["raw"] for r in erows);size=sum(r["size"] for r in erows)
    ct=sum(r["comp_time_s"] for r in erows);dt=sum(r["dec_time_s"] for r in erows)
    ep=dict(epoch=epoch,raw=raw,size=size,ratio=size/raw,comp_time_s=ct,dec_time_s=dt,
            comp_MBps=raw/1e6/ct,probes=sum(r["probes"] for r in erows),wins=sum(r["wins"] for r in erows),
            gain_bytes=sum(r["gain_bytes"] for r in erows),probe_cost_s=sum(r["probe_cost_s"] for r in erows),
            model_buckets=len(model),sha_all=all(r["sha_ok"] for r in erows))
    epochs.append({"summary":ep,"rows":erows})
    print("EPOCH",json.dumps(ep,sort_keys=True),flush=True)
Path("exp70_model.json").write_text(json.dumps(model,indent=2,sort_keys=True))
Path("exp70_results.json").write_text(json.dumps({"epochs":epochs,"model":model},indent=2))
print("FINAL",json.dumps([e["summary"] for e in epochs],indent=2),flush=True)
