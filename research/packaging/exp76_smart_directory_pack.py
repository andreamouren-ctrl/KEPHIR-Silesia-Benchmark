from pathlib import Path
import subprocess, time, json, hashlib, os, math, collections, importlib, sys, struct, shutil, tempfile

MAGIC=b"K76D"
VERSION=1
OUT=Path("exp76_directory_pack")
OUT.mkdir(exist_ok=True)

def git_files():
    raw=subprocess.check_output(["git","ls-files","-z"])
    return [Path(x.decode("utf-8")) for x in raw.split(b"\0") if x]

def file_bytes(p):
    if p.is_symlink():
        return os.readlink(p).encode("utf-8")
    return p.read_bytes()

def entropy(vals):
    if not vals: return 0.0
    c=collections.Counter(vals); n=len(vals)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def classify(data):
    # Content-first classifier: names/extensions are deliberately ignored.
    if not data:
        return "empty"
    step=max(1,len(data)//8192)
    s=data[::step]
    n=len(s)
    printable=sum(1 for b in s if b in (9,10,13) or 32<=b<127)/n
    letters_space=sum(1 for b in s if b==32 or 65<=b<=90 or 97<=b<=122)/n
    zero=s.count(0)/n
    h=entropy(s)

    if len(data)<=192:
        return "tiny-text" if printable>=0.85 else "tiny-binary"

    if printable>=0.88:
        b64set=b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n"
        b64ratio=sum(1 for b in s if b in b64set)/n
        if b64ratio>=0.985 and 4.0<=h<=6.5:
            return "encoded-text"

        codepun=sum(1 for b in s if b in b"(){}[];=_<>")/n
        configpun=sum(1 for b in s if b in b":-\"'")/n
        nl=s.count(10)/n
        if codepun>=0.028:
            return "text-code"
        if configpun>=0.035 and nl>=0.010:
            return "text-config"
        if letters_space>=0.63:
            return "text-prose"
        return "text-generic"

    if zero>=0.08:
        return "binary-zero"
    if h<5.5:
        return "binary-low"
    if h<7.3:
        return "binary-mid"
    return "binary-high"

def put_varint(out,v):
    v=int(v)
    while True:
        b=v & 0x7f; v >>= 7
        if v: out.append(b|0x80)
        else:
            out.append(b); break

def get_varint(buf,pos):
    shift=0; v=0
    while True:
        b=buf[pos]; pos+=1
        v |= (b & 0x7f)<<shift
        if not (b&0x80): return v,pos
        shift+=7
        if shift>63: raise ValueError("varint overflow")

def common_prefix(a,b):
    n=min(len(a),len(b)); i=0
    while i<n and a[i]==b[i]: i+=1
    return i

def sha256(b):
    return hashlib.sha256(b).hexdigest()

# Make EXP-75 importable by ProcessPool workers.
src=Path("research/routers/exp75_lazy_wx_fingerprint.py").read_text()
prefix=src.split("\nCORPORA=[",1)[0]
Path("kephir_exp75_lib.py").write_text(prefix)
importlib.invalidate_caches()
if str(Path.cwd()) not in sys.path:
    sys.path.insert(0,str(Path.cwd()))
k=importlib.import_module("kephir_exp75_lib")

def encode_k75(raw_path,arc_path,tmp,model):
    tmp.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    k.encode(raw_path,arc_path,tmp,model)
    return time.perf_counter()-t

def decode_k75(arc_path,out_path,tmp):
    tmp.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    k.decode(arc_path,out_path,tmp)
    return time.perf_counter()-t

def build_manifest(records,group_ids):
    # Records sorted by path. Path prefix compression + varints.
    out=bytearray()
    put_varint(out,len(records))
    prev=b""
    for r in records:
        p=r["path"].encode("utf-8")
        cp=common_prefix(prev,p)
        suf=p[cp:]
        put_varint(out,cp)
        put_varint(out,len(suf))
        out.extend(suf)
        put_varint(out,group_ids[r["group"]])
        put_varint(out,r["size"])
        prev=p
    return bytes(out)

def parse_manifest(buf,pos,group_names):
    count,pos=get_varint(buf,pos)
    prev=b""; recs=[]
    for _ in range(count):
        cp,pos=get_varint(buf,pos)
        sl,pos=get_varint(buf,pos)
        suf=buf[pos:pos+sl]; pos+=sl
        path=prev[:cp]+suf
        gid,pos=get_varint(buf,pos)
        size,pos=get_varint(buf,pos)
        recs.append({"path":path.decode("utf-8"),"group":group_names[gid],"size":size})
        prev=path
    return recs,pos

def smart_pack(files,archive):
    records=[]
    groups=collections.defaultdict(bytearray)
    for p in sorted(files,key=lambda x:str(x)):
        data=file_bytes(p)
        g=classify(data)
        records.append({"path":str(p).replace(os.sep,"/"),"group":g,"size":len(data),"sha256":sha256(data)})
        groups[g].extend(data)

    group_names=sorted(groups)
    gids={g:i for i,g in enumerate(group_names)}
    manifest=build_manifest(records,gids)

    work=OUT/"smart_work"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()
    model={}
    compressed=[]
    comp_s=0.0
    for gid,g in enumerate(group_names):
        raw=work/f"g{gid}.raw"; arc=work/f"g{gid}.k75"
        raw.write_bytes(groups[g])
        comp_s += encode_k75(raw,arc,work/f"tmp_g{gid}",model)
        compressed.append((g,len(groups[g]),arc.read_bytes()))

    out=bytearray(MAGIC)
    out.extend(struct.pack("<B",VERSION))
    put_varint(out,len(group_names))
    for g in group_names:
        gb=g.encode("utf-8"); put_varint(out,len(gb)); out.extend(gb)
    put_varint(out,len(manifest)); out.extend(manifest)
    for g,rawlen,cdata in compressed:
        put_varint(out,rawlen)
        put_varint(out,len(cdata))
        out.extend(cdata)
    archive.write_bytes(out)
    return records,group_names,comp_s,{g:len(groups[g]) for g in group_names},len(manifest)

def smart_unpack(archive,outdir):
    b=archive.read_bytes(); pos=0
    if b[:4]!=MAGIC: raise ValueError("bad magic")
    pos=4
    ver=b[pos]; pos+=1
    if ver!=VERSION: raise ValueError("bad version")
    ng,pos=get_varint(b,pos)
    names=[]
    for _ in range(ng):
        n,pos=get_varint(b,pos)
        names.append(b[pos:pos+n].decode("utf-8")); pos+=n
    ml,pos=get_varint(b,pos)
    manifest=b[pos:pos+ml]; pos+=ml
    recs,_=parse_manifest(manifest,0,names)

    work=OUT/"unpack_work"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()
    rawgroups={}
    dec_s=0.0
    for gid,g in enumerate(names):
        rawlen,pos=get_varint(b,pos)
        clen,pos=get_varint(b,pos)
        cdata=b[pos:pos+clen]; pos+=clen
        arc=work/f"g{gid}.k75"; raw=work/f"g{gid}.raw"
        arc.write_bytes(cdata)
        dec_s += decode_k75(arc,raw,work/f"tmp_g{gid}")
        data=raw.read_bytes()
        if len(data)!=rawlen: raise ValueError("group length mismatch")
        rawgroups[g]=data

    cursors={g:0 for g in names}
    if outdir.exists(): shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    for r in recs:
        g=r["group"]; off=cursors[g]; n=r["size"]
        data=rawgroups[g][off:off+n]
        cursors[g]=off+n
        p=outdir/r["path"]; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(data)
    return recs,dec_s

def verify_original(files,outdir):
    for p in files:
        a=file_bytes(p); q=outdir/str(p)
        if not q.exists() or q.read_bytes()!=a:
            return False,str(p)
    return True,None

def deterministic_flat_payload(files,path):
    # Same logical bytes plus compact framing; unlike TAR it avoids 512-byte
    # headers/padding so the comparison isolates grouping rather than TAR overhead.
    out=bytearray()
    for p in sorted(files,key=lambda x:str(x)):
        data=file_bytes(p); pb=str(p).encode()
        put_varint(out,len(pb)); out.extend(pb); put_varint(out,len(data)); out.extend(data)
    path.write_bytes(out)

def flat_k75(files):
    raw=OUT/"flat_payload.bin"; arc=OUT/"flat_payload.k75"; dec=OUT/"flat_payload.dec"
    deterministic_flat_payload(files,raw)
    model={}
    ct=encode_k75(raw,arc,OUT/"flat_tmp",model)
    dt=decode_k75(arc,dec,OUT/"flat_dtmp")
    ok=raw.read_bytes()==dec.read_bytes()
    return {"size":arc.stat().st_size,"comp_time_s":ct,"dec_time_s":dt,"sha_ok":ok,"input_bytes":raw.stat().st_size}

def per_file_k75(files):
    root=OUT/"pf"
    if root.exists(): shutil.rmtree(root)
    root.mkdir()
    model={}
    size=0; ct=0.0; dt=0.0
    for i,p in enumerate(sorted(files,key=lambda x:str(x))):
        raw=root/f"{i}.raw"; arc=root/f"{i}.k75"; dec=root/f"{i}.dec"
        raw.write_bytes(file_bytes(p))
        ct+=encode_k75(raw,arc,root/f"t{i}",model)
        dt+=decode_k75(arc,dec,root/f"d{i}")
        if raw.read_bytes()!=dec.read_bytes(): raise RuntimeError("per-file SHA fail "+str(p))
        size+=arc.stat().st_size
    return {"size":size,"comp_time_s":ct,"dec_time_s":dt,"sha_ok":True}

files=git_files()
logical=sum(len(file_bytes(p)) for p in files)

archive=OUT/"repository.k76d"
records,group_names,smart_ct,group_bytes,manifest_bytes=smart_pack(files,archive)
recs,smart_dt=smart_unpack(archive,OUT/"restored")
smart_ok,bad=verify_original(files,OUT/"restored")
if not smart_ok: raise RuntimeError("smart restore mismatch "+str(bad))

flat=flat_k75(files)
perfile=per_file_k75(files)

result={
    "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
    "tracked_files":len(files),
    "logical_bytes":logical,
    "groups":group_names,
    "group_bytes":group_bytes,
    "manifest_bytes":manifest_bytes,
    "smart":{"size":archive.stat().st_size,"ratio":archive.stat().st_size/logical if logical else 0,
             "comp_time_s":smart_ct,"dec_time_s":smart_dt,"sha_ok":smart_ok},
    "flat":{"size":flat["size"],"ratio":flat["size"]/logical if logical else 0,
            "comp_time_s":flat["comp_time_s"],"dec_time_s":flat["dec_time_s"],"sha_ok":flat["sha_ok"],
            "framed_input_bytes":flat["input_bytes"]},
    "per_file":{"size":perfile["size"],"ratio":perfile["size"]/logical if logical else 0,
                "comp_time_s":perfile["comp_time_s"],"dec_time_s":perfile["dec_time_s"],"sha_ok":perfile["sha_ok"]},
}
Path("exp76_results.json").write_text(json.dumps(result,indent=2,sort_keys=True))

print("EXP76_RESULT",json.dumps(result,sort_keys=True),flush=True)
