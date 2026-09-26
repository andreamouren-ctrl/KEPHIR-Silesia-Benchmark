from pathlib import Path
import subprocess,struct,hashlib,time,json,shutil,collections,math,concurrent.futures

MAGIC=b"K63U"
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

def transform(buf,mode):
    if mode==0:return buf
    if mode==1:return transpose(delta_lag(buf,4),4)
    if mode==2:return transpose(delta_lag(buf,1024),1024)
    if mode==4:return transpose(delta_lag(buf,2),2)
    if mode==5:return transpose(delta_lag(buf,16),16)
    if mode==6:return text_tokenize(buf)
    raise ValueError(mode)

def inverse(buf,mode,rawlen):
    if mode==0:return buf
    if mode==1:return inv_delta(inv_transpose(buf,4,rawlen),4)
    if mode==2:return inv_delta(inv_transpose(buf,1024,rawlen),1024)
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

def encode(src,dst,tmp):
    raw=src.read_bytes();entries=[];chosen=collections.Counter();grains=collections.Counter()
    tasks=[]
    for pidx,start in enumerate(range(0,len(raw),CH)):
        parent=raw[start:start+CH]
        grain=choose_grain(parent)
        for j,off in enumerate(range(0,len(parent),grain)):
            tasks.append((pidx,j,parent[off:off+grain]))

    def process_one(task):
        pidx,j,chunk=task
        mode=choose_mode(chunk)
        payload=transform(chunk,mode)
        comp=cp(payload,tmp/f"p{pidx}_{j}_m{mode}")
        if mode!=0:
            base_comp=cp(chunk,tmp/f"p{pidx}_{j}_basecheck")
            if len(base_comp)<=len(comp):
                mode=0
                comp=base_comp
        if is_text_like(chunk):
            tok=text_tokenize(chunk)
            if len(tok)+16 < len(chunk)*0.99:
                tok_comp=cp(tok,tmp/f"p{pidx}_{j}_text")
                if len(tok_comp)<len(comp):
                    mode=6
                    comp=tok_comp
        return mode,len(chunk),comp

    # EXP-63 single conceptual change: process independent chunks concurrently.
    # Two workers match the two-vCPU GitHub runner and keep deterministic output
    # because executor.map preserves task order.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        entries=list(ex.map(process_one,tasks))

    for mode,n,comp in entries:
        chosen[mode]+=1;grains[n]+=1
    with dst.open("wb") as f:
        f.write(MAGIC);f.write(struct.pack("<QI",len(raw),len(entries)))
        for mode,n,comp in entries:
            f.write(struct.pack("<BII",mode,n,len(comp)));f.write(comp)
    return chosen,grains

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

root=Path("silesia");out=Path("exp63_out");tmp=out/"tmp"
out.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
rows=[]
for fn in FILES:
    src=root/fn;arc=out/f"{fn}.k63";dec=out/f"{fn}.dec"
    t=time.perf_counter();chosen,grains=encode(src,arc,tmp);ct=time.perf_counter()-t
    t=time.perf_counter();decode(arc,dec,tmp);dt=time.perf_counter()-t
    ok=hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dec.read_bytes()).digest()
    if not ok: raise SystemExit("SHA FAIL "+fn)
    raw=src.stat().st_size;size=arc.stat().st_size
    row=dict(file=fn,raw=raw,size=size,ratio=size/raw,
             comp_time_s=ct,dec_time_s=dt,
             comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt,
             modes={str(k):v for k,v in sorted(chosen.items())},
             grains={str(k):v for k,v in sorted(grains.items())},
             sha_ok=ok)
    rows.append(row);print(row,flush=True)
    dec.unlink()

raw=sum(r["raw"] for r in rows);size=sum(r["size"] for r in rows)
ct=sum(r["comp_time_s"] for r in rows);dt=sum(r["dec_time_s"] for r in rows)
modes=collections.Counter();grains=collections.Counter()
for r in rows:
    modes.update(r["modes"]);grains.update(r["grains"])
summary=dict(
    raw=raw,size=size,ratio=size/raw,
    comp_time_s=ct,dec_time_s=dt,
    comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,
    sha_all=all(r["sha_ok"] for r in rows),
    modes=dict(modes),grains=dict(grains),
    baseline_exp62_size=63454863,
    delta_vs_exp62_bytes=size-63454863,
    ratio_delta_vs_exp62_pp=(size/raw-63454863/raw)*100.0,
    baseline_exp60_size=63609809,
    delta_vs_exp60_bytes=size-63609809,
    ratio_delta_vs_exp60_pp=(size/raw-63609809/raw)*100.0,
    baseline_exp59_size=63609809,
    delta_vs_exp59_bytes=size-63609809,
    ratio_delta_vs_exp59_pp=(size/raw-63609809/raw)*100.0,
    baseline_exp58_size=63745538,
    delta_vs_exp58_bytes=size-63745538,
    ratio_delta_vs_exp58_pp=(size/raw-63745538/raw)*100.0,
    baseline_exp56_size=63002080,
    delta_bytes=size-63002080,
    ratio_delta_pp=(size/raw-63002080/raw)*100.0,
    target_time_s=60.0,
    within_60s=ct<=60.0
)
print("SUMMARY",json.dumps(summary,indent=2),flush=True)
Path("exp63_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
