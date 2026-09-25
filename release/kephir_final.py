#!/usr/bin/env python3
"""
KEPHIR 1.0 Final Candidate
Integrated lossless compressor orchestration layer.

Validated techniques integrated:
- EXP-37 arithmetic/back-end core
- structural transforms and exact BASE verification
- EXP-60 indexed reversible text tokenization
- EXP-66 cost-aware LPT work parcels / ProcessPool
- EXP-72 adaptive grain learning (128/256/512 KiB)
- EXP-75 lazy predictive Word-XOR gate
- EXP-76 content-first smart directory packing
- Factory + Local + Session experience
- deterministic self-describing archives; decoder needs no learned state
"""

from pathlib import Path
import argparse, collections, concurrent.futures, copy, hashlib, importlib, json, math
import os, shutil, struct, sys, tempfile, time

VERSION="1.0.0-rc1"
MAGIC=b"KPF1"
TYPE_FILE=0
TYPE_DIRECTORY=1
FACTORY_PATH=Path(__file__).resolve().parent/"factory"/"khepri_factory_v1.json"
LOCAL_SCHEMA=1
STATE_FIELDS=("seen","trials","wins","gain","cost")

def _load_engine():
    root=Path(__file__).resolve().parents[1]
    p=root/"research"/"routers"/"exp75_lazy_wx_fingerprint.py"
    code=p.read_text()
    prefix=code.split("\nCORPORA=[",1)[0]
    modpath=root/"release"/"_kephir_engine_runtime.py"
    # Materialize only the engine definitions so multiprocessing can import them.
    if not modpath.exists() or modpath.read_text()!=prefix:
        modpath.write_text(prefix)
    if str(modpath.parent) not in sys.path:
        sys.path.insert(0,str(modpath.parent))
    importlib.invalidate_caches()
    return importlib.import_module("_kephir_engine_runtime")

E=_load_engine()

def put_varint(out,v):
    v=int(v)
    if v<0: raise ValueError("negative varint")
    while True:
        b=v&0x7f; v>>=7
        if v: out.append(b|0x80)
        else: out.append(b); return

def get_varint(buf,pos):
    v=0; shift=0
    while True:
        if pos>=len(buf): raise ValueError("truncated varint")
        b=buf[pos]; pos+=1
        v|=(b&0x7f)<<shift
        if not (b&0x80): return v,pos
        shift+=7
        if shift>63: raise ValueError("varint overflow")

def common_prefix(a,b):
    n=min(len(a),len(b)); i=0
    while i<n and a[i]==b[i]: i+=1
    return i

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def entropy(vals):
    if not vals:return 0.0
    c=collections.Counter(vals); n=len(vals)
    return -sum((x/n)*math.log2(x/n) for x in c.values())

def classify(data):
    # Content-first: extension/name is intentionally irrelevant.
    if not data:return "empty"
    step=max(1,len(data)//8192)
    s=data[::step]; n=len(s)
    printable=sum(1 for b in s if b in (9,10,13) or 32<=b<127)/n
    letters_space=sum(1 for b in s if b==32 or 65<=b<=90 or 97<=b<=122)/n
    zero=s.count(0)/n; h=entropy(s)
    if len(data)<=192:return "tiny-text" if printable>=0.85 else "tiny-binary"
    if printable>=0.88:
        b64set=b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n"
        if sum(1 for b in s if b in b64set)/n>=0.985 and 4.0<=h<=6.5:return "encoded-text"
        codepun=sum(1 for b in s if b in b"(){}[];=_<>")/n
        configpun=sum(1 for b in s if b in b":-\"'")/n
        nl=s.count(10)/n
        if codepun>=0.028:return "text-code"
        if configpun>=0.035 and nl>=0.010:return "text-config"
        if letters_space>=0.63:return "text-prose"
        return "text-generic"
    if zero>=0.08:return "binary-zero"
    if h<5.5:return "binary-low"
    if h<7.3:return "binary-mid"
    return "binary-high"

def default_local_path():
    base=Path(os.environ.get("KEPHIR_HOME",Path.home()/".kephir"))
    return base/"khepri_local_v1.json"

def load_factory(enabled=True):
    if not enabled:return {}
    d=json.loads(FACTORY_PATH.read_text())
    if d.get("schema")!=1: raise ValueError("unsupported factory knowledge schema")
    return d.get("states",{})

def load_local(path,enabled=True):
    if not enabled or not path.exists():return {}
    try:
        d=json.loads(path.read_text())
        if d.get("schema")!=LOCAL_SCHEMA:return {}
        return d.get("states",{})
    except Exception:
        return {}

def merge_models(factory,local):
    keys=set(factory)|set(local); out={}
    for k in keys:
        a=factory.get(k,{}); b=local.get(k,{})
        out[k]={}
        for f in STATE_FIELDS:
            out[k][f]=a.get(f,0)+b.get(f,0)
    return out

def local_overlay(model,factory):
    out={}
    for k,v in model.items():
        a=factory.get(k,{})
        st={}
        for f in STATE_FIELDS:
            x=v.get(f,0)-a.get(f,0)
            if f=="cost": x=max(0.0,float(x))
            else: x=max(0,int(round(x)))
            st[f]=x
        if any(st[f] for f in STATE_FIELDS):
            out[k]=st
    return out

def atomic_save_local(path,states):
    path.parent.mkdir(parents=True,exist_ok=True)
    payload={"schema":LOCAL_SCHEMA,"engine":"KEPHIR-1.0","factory":"v1","states":states}
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True))
    os.replace(tmp,path)

def trusted_grain(parent,model):
    """Use factory/local prior only when repeated wins are strong enough."""
    baseline=E.choose_grain(parent)
    key=E.grain_feature_bucket(parent)
    candidates=[]
    if len(parent)>128*1024:candidates.append(128*1024)
    if len(parent)>256*1024:candidates.append(256*1024)
    candidates.append(len(parent))
    best=None
    for g in sorted(set(candidates)):
        st=model.get(f"{key}|g{g}")
        if not st:continue
        tr=max(1,st.get("trials",0)); wr=st.get("wins",0)/tr
        avg=st.get("gain",0)/tr
        # conservative cross-file generalization gate
        if tr>=3 and wr>=0.80 and avg>=256:
            score=(avg*wr,tr)
            if best is None or score>best[0]:best=(score,g)
    return (best[1] if best else baseline),key,bool(best)

def final_encode(src,dst,tmp,model):
    tmp.mkdir(parents=True,exist_ok=True)
    raw=src.read_bytes(); tasks=[]; seq=0
    chosen=collections.Counter(); grains=collections.Counter()
    prior_hits=0; grain_probes=grain_wins=grain_gain_bytes=0; grain_probe_cost_s=0.0

    for pidx,start in enumerate(range(0,len(raw),E.CH)):
        parent=raw[start:start+E.CH]
        grain,key,prior=trusted_grain(parent,model)
        if prior: prior_hits+=1
        baseline=grain

        candidates=[]
        if len(parent)>128*1024:candidates.append(128*1024)
        if len(parent)>256*1024:candidates.append(256*1024)
        candidates.append(len(parent))
        candidates=sorted(set(candidates))

        # Known high-confidence family: trust the shipped/local experience.
        # Unknown/uncertain family: retain EXP-72 controlled exploration.
        probes=[] if prior else [g for g in candidates if g!=baseline and E.grain_should_probe(model,key,g)]
        if probes:
            t0=time.perf_counter()
            baseline_size=E.measure_grain_exact(parent,baseline,tmp,pidx,"base")
            grain_probe_cost_s+=time.perf_counter()-t0
            best_size=baseline_size; best_grain=baseline
            for g in probes:
                t=time.perf_counter()
                alt=E.measure_grain_exact(parent,g,tmp,pidx,f"g{g}")
                cost=time.perf_counter()-t
                grain_probe_cost_s+=cost
                gain=baseline_size-alt
                E.grain_update(model,key,g,gain,cost)
                grain_probes+=1
                if alt<best_size:best_size=alt;best_grain=g
            grain=best_grain
            realized=max(0,baseline_size-best_size)
            if realized>0:grain_wins+=1;grain_gain_bytes+=realized

        for j,off in enumerate(range(0,len(parent),grain)):
            chunk=parent[off:off+grain]
            coarse=E.wx_coarse_bucket(chunk)
            wx_key=coarse; wx_probe=False
            if coarse in E.FACTORY_WX_COARSE and not E.is_text_like(chunk):
                wx_key=E.chunk_feature_bucket(chunk,coarse)
                wx_probe=E.wx_should_probe(model,wx_key)
            tasks.append((seq,pidx,j,chunk,wx_probe,wx_key))
            seq+=1

    requested=max(1,min(16,int(os.environ.get("KEPHIR_WORKERS","16"))))
    workers=max(1,min(requested,os.cpu_count() or 1,len(tasks) or 1))
    target=max(workers,min(len(tasks),workers*3)) if tasks else 0
    bins=[[] for _ in range(target)] if target else []
    loads=[0.0]*target
    for task in sorted(tasks,key=lambda t:E.estimate_task_cost(t[3]),reverse=True):
        bi=min(range(target),key=lambda k:loads[k])
        bins[bi].append(task); loads[bi]+=E.estimate_task_cost(task[3])
    parcels=[p for p in bins if p]

    if parcels:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
            prs=list(ex.map(E.process_parcel,[(p,str(tmp)) for p in parcels],chunksize=1))
        flat=[x for p in prs for x in p]
    else: flat=[]
    flat.sort(key=lambda x:x[0])

    entries=[(mode,n,comp) for _,mode,n,comp,_,_,_,_ in flat]
    wx_probes=wx_wins=wx_gain=0; wx_cost=0.0
    for _,_,_,_,key,probed,gain,cost in flat:
        if probed:
            wx_probes+=1; wx_wins+=int(gain>0); wx_gain+=gain; wx_cost+=cost
            E.wx_update(model,key,gain,cost)
    for mode,n,comp in entries:
        chosen[mode]+=1; grains[n]+=1

    with dst.open("wb") as f:
        f.write(E.MAGIC); f.write(struct.pack("<QI",len(raw),len(entries)))
        for mode,n,comp in entries:
            f.write(struct.pack("<BII",mode,n,len(comp))); f.write(comp)

    return {
      "prior_grain_hits":prior_hits,"grain_probes":grain_probes,"grain_wins":grain_wins,
      "grain_gain_bytes":grain_gain_bytes,"grain_probe_cost_s":grain_probe_cost_s,
      "wx_probes":wx_probes,"wx_wins":wx_wins,"wx_gain_bytes":wx_gain,"wx_probe_cost_s":wx_cost,
      "modes":dict(chosen),"grains":{str(k):v for k,v in grains.items()},
      "workers":workers,"parcels":len(parcels)
    }

def final_decode(src,dst,tmp):
    tmp.mkdir(parents=True,exist_ok=True)
    return E.decode(src,dst,tmp)

def build_manifest(records,group_ids):
    out=bytearray();put_varint(out,len(records));prev=b""
    for r in records:
        p=r["path"].encode("utf-8");cp=common_prefix(prev,p);suf=p[cp:]
        put_varint(out,cp);put_varint(out,len(suf));out.extend(suf)
        put_varint(out,group_ids[r["group"]]);put_varint(out,r["size"])
        prev=p
    return bytes(out)

def parse_manifest(buf,names):
    pos=0;count,pos=get_varint(buf,pos);prev=b"";recs=[]
    for _ in range(count):
        cp,pos=get_varint(buf,pos);sl,pos=get_varint(buf,pos);suf=buf[pos:pos+sl];pos+=sl
        gid,pos=get_varint(buf,pos);size,pos=get_varint(buf,pos)
        p=prev[:cp]+suf;prev=p
        recs.append({"path":p.decode("utf-8"),"group":names[gid],"size":size})
    return recs

def safe_target(root,rel):
    p=Path(rel)
    if p.is_absolute() or ".." in p.parts:raise ValueError("unsafe archive path")
    dest=(root/p).resolve()
    rr=root.resolve()
    if dest!=rr and rr not in dest.parents:raise ValueError("unsafe archive path")
    return dest

def collect_directory(root):
    files=[p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]
    return sorted(files,key=lambda p:p.relative_to(root).as_posix())

def compress_file(inp,out,model,tmp):
    inner=tmp/"file.k75"
    stats=final_encode(inp,inner,tmp/"engine",model)
    name=inp.name.encode("utf-8"); blob=inner.read_bytes()
    data=bytearray(MAGIC);data.append(TYPE_FILE)
    put_varint(data,len(name));data.extend(name);put_varint(data,len(blob));data.extend(blob)
    out.write_bytes(data)
    return stats

def compress_directory(root,out,model,tmp):
    records=[];groups=collections.defaultdict(bytearray)
    for p in collect_directory(root):
        raw=p.read_bytes();g=classify(raw)
        records.append({"path":p.relative_to(root).as_posix(),"group":g,"size":len(raw)})
        groups[g].extend(raw)
    names=sorted(groups);gids={g:i for i,g in enumerate(names)}
    manifest=build_manifest(records,gids)

    data=bytearray(MAGIC);data.append(TYPE_DIRECTORY)
    put_varint(data,len(names))
    for g in names:
        b=g.encode();put_varint(data,len(b));data.extend(b)
    put_varint(data,len(manifest));data.extend(manifest)

    group_stats={}
    for i,g in enumerate(names):
        rp=tmp/f"g{i}.raw";ap=tmp/f"g{i}.k75"
        rp.write_bytes(groups[g])
        group_stats[g]=final_encode(rp,ap,tmp/f"e{i}",model)
        blob=ap.read_bytes();put_varint(data,len(groups[g]));put_varint(data,len(blob));data.extend(blob)
    out.write_bytes(data)
    return {"groups":{g:len(groups[g]) for g in names},"manifest_bytes":len(manifest),"engine":group_stats}

def extract_archive(arc,out,tmp):
    b=arc.read_bytes();pos=0
    if b[:4]!=MAGIC:raise ValueError("not a KEPHIR 1.0 archive")
    pos=4;kind=b[pos];pos+=1
    if kind==TYPE_FILE:
        nl,pos=get_varint(b,pos);name=b[pos:pos+nl].decode();pos+=nl
        cl,pos=get_varint(b,pos);blob=b[pos:pos+cl]
        inner=tmp/"file.k75";inner.write_bytes(blob)
        target=out if (out.exists() and out.is_file()) or out.suffix else out/name
        target.parent.mkdir(parents=True,exist_ok=True)
        final_decode(inner,target,tmp/"d")
        return [target]
    if kind!=TYPE_DIRECTORY:raise ValueError("unknown archive kind")
    ng,pos=get_varint(b,pos);names=[]
    for _ in range(ng):
        n,pos=get_varint(b,pos);names.append(b[pos:pos+n].decode());pos+=n
    ml,pos=get_varint(b,pos);manifest=b[pos:pos+ml];pos+=ml
    recs=parse_manifest(manifest,names)
    rawgroups={}
    for i,g in enumerate(names):
        rawlen,pos=get_varint(b,pos);cl,pos=get_varint(b,pos);blob=b[pos:pos+cl];pos+=cl
        ap=tmp/f"g{i}.k75";rp=tmp/f"g{i}.raw";ap.write_bytes(blob)
        final_decode(ap,rp,tmp/f"d{i}")
        raw=rp.read_bytes()
        if len(raw)!=rawlen:raise ValueError("group length mismatch")
        rawgroups[g]=raw
    curs={g:0 for g in names};written=[]
    out.mkdir(parents=True,exist_ok=True)
    for r in recs:
        g=r["group"];off=curs[g];n=r["size"];raw=rawgroups[g][off:off+n];curs[g]=off+n
        p=safe_target(out,r["path"]);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);written.append(p)
    return written

def info_archive(p):
    b=p.read_bytes()
    if b[:4]!=MAGIC:raise ValueError("not a KEPHIR 1.0 archive")
    kind=b[4]
    return {"version":VERSION,"type":"file" if kind==TYPE_FILE else "directory","archive_bytes":len(b)}

def verify_roundtrip(inp,arc):
    with tempfile.TemporaryDirectory(prefix="kephir_verify_") as td:
        td=Path(td);dest=td/"out"
        extract_archive(arc,dest,td/"tmp")
        if inp.is_file():
            out=dest/inp.name
            if not out.exists(): out=dest
            return out.exists() and sha256_file(inp)==sha256_file(out)
        original=collect_directory(inp)
        for p in original:
            q=dest/p.relative_to(inp)
            if not q.exists() or sha256_file(p)!=sha256_file(q):return False
        return True

def cmd_compress(args):
    inp=Path(args.input).resolve();out=Path(args.output).resolve()
    factory=load_factory(not args.cold)
    local_path=Path(args.local_knowledge).expanduser() if args.local_knowledge else default_local_path()
    local=load_local(local_path,not args.cold and not args.no_local)
    model=merge_models(factory,local)
    os.environ["KEPHIR_WORKERS"]=str(args.workers)
    out.parent.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="kephir_") as td:
        tmp=Path(td)
        stats=compress_file(inp,out,model,tmp) if inp.is_file() else compress_directory(inp,out,model,tmp)
    elapsed=time.perf_counter()-t
    ok=True
    if args.verify:ok=verify_roundtrip(inp,out)
    if not ok:
        out.unlink(missing_ok=True);raise SystemExit("lossless verification failed")
    if not args.cold and not args.no_local:
        atomic_save_local(local_path,local_overlay(model,factory))
    raw=inp.stat().st_size if inp.is_file() else sum(p.stat().st_size for p in collect_directory(inp))
    print(json.dumps({"version":VERSION,"input_bytes":raw,"archive_bytes":out.stat().st_size,
      "ratio":out.stat().st_size/raw if raw else 0,"time_s":elapsed,"verified":ok,"stats":stats},sort_keys=True))

def cmd_extract(args):
    arc=Path(args.archive).resolve();out=Path(args.output).resolve()
    t=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="kephir_extract_") as td:
        written=extract_archive(arc,out,Path(td))
    print(json.dumps({"version":VERSION,"files":len(written),"time_s":time.perf_counter()-t},sort_keys=True))

def main():
    ap=argparse.ArgumentParser(prog="kephir",description="KEPHIR 1.0 lossless compressor final candidate")
    ap.add_argument("--version",action="version",version=VERSION)
    sp=ap.add_subparsers(dest="cmd",required=True)
    c=sp.add_parser("compress");c.add_argument("input");c.add_argument("output")
    c.add_argument("--workers",type=int,default=min(16,os.cpu_count() or 1))
    c.add_argument("--cold",action="store_true",help="disable Factory and Local Experience")
    c.add_argument("--no-local",action="store_true",help="use Factory Experience but do not load/save local overlay")
    c.add_argument("--local-knowledge",default=None)
    c.add_argument("--verify",action=argparse.BooleanOptionalAction,default=True)
    c.set_defaults(func=cmd_compress)
    x=sp.add_parser("extract");x.add_argument("archive");x.add_argument("output");x.set_defaults(func=cmd_extract)
    i=sp.add_parser("info");i.add_argument("archive");i.set_defaults(func=lambda a:print(json.dumps(info_archive(Path(a.archive)),sort_keys=True)))
    a=ap.parse_args();a.func(a)

if __name__=="__main__":main()
