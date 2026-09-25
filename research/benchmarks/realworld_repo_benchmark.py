from pathlib import Path
import subprocess, time, json, hashlib, tarfile, io, os, shutil, tempfile, collections, shlex

OUT=Path("realworld_repo_benchmark")
OUT.mkdir(exist_ok=True)
TMP=OUT/"tmp"
if TMP.exists(): shutil.rmtree(TMP)
TMP.mkdir()

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def git_files():
    raw=subprocess.check_output(["git","ls-files","-z"])
    return [Path(x.decode("utf-8")) for x in raw.split(b"\0") if x]

FILES=git_files()

def blob_bytes(p):
    if p.is_symlink():
        return os.readlink(p).encode("utf-8")
    return p.read_bytes()

def make_deterministic_tar(files,dst):
    with tarfile.open(dst,"w",format=tarfile.PAX_FORMAT) as tf:
        for p in files:
            data=blob_bytes(p)
            ti=tarfile.TarInfo(str(p).replace(os.sep,"/"))
            ti.size=len(data); ti.mtime=0; ti.uid=0; ti.gid=0
            ti.uname=""; ti.gname=""; ti.mode=0o644
            tf.addfile(ti,io.BytesIO(data))

def timed(cmd,stdout_path=None,cwd=None):
    t=time.perf_counter()
    if stdout_path is None:
        subprocess.run(cmd,check=True,cwd=cwd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        with open(stdout_path,"wb") as f:
            subprocess.run(cmd,check=True,cwd=cwd,stdout=f,stderr=subprocess.DEVNULL)
    return time.perf_counter()-t

def competitor_solid(name,src):
    d=OUT/"solid"/name
    d.mkdir(parents=True,exist_ok=True)
    arc=d/"archive.bin"; dec=d/"decoded.tar"
    if name=="7z-LZMA2":
        arc=d/"archive.7z"
        ct=timed(["7z","a","-bd","-y","-t7z","-mx=9","-m0=lzma2","-mmt=on",str(arc),str(src)])
        dt=timed(["7z","e","-so",str(arc)],stdout_path=dec)
    elif name=="ZIP-Deflate":
        arc=d/"archive.zip"
        ct=timed(["zip","-q","-9","-j",str(arc),str(src)])
        dt=timed(["unzip","-p",str(arc)],stdout_path=dec)
    elif name=="XZ-LZMA2":
        ct=timed(["xz","-9","-T0","-c",str(src)],stdout_path=arc)
        dt=timed(["xz","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Zstd-19":
        ct=timed(["zstd","-19","-T0","-q","-c",str(src)],stdout_path=arc)
        dt=timed(["zstd","-d","-q","-c",str(arc)],stdout_path=dec)
    elif name=="Brotli-11":
        ct=timed(["brotli","-q","11","-c",str(src)],stdout_path=arc)
        dt=timed(["brotli","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Bzip2-9":
        ct=timed(["bzip2","-9","-c",str(src)],stdout_path=arc)
        dt=timed(["bzip2","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Gzip-9":
        ct=timed(["gzip","-n","-9","-c",str(src)],stdout_path=arc)
        dt=timed(["gzip","-d","-c",str(arc)],stdout_path=dec)
    elif name=="LZ4-HC":
        ct=timed(["lz4","-9","-q",str(src),str(arc)])
        dt=timed(["lz4","-d","-q",str(arc),str(dec)])
    else:
        raise ValueError(name)
    ok=sha256_file(src)==sha256_file(dec)
    if not ok: raise RuntimeError(name+" solid SHA mismatch")
    return dict(name=name,size=arc.stat().st_size,comp_time_s=ct,dec_time_s=dt,sha_ok=ok)

# Load EXP-75 core without executing its corpus benchmark main.
code=Path("research/routers/exp75_lazy_wx_fingerprint.py").read_text()
prefix=code.split("\nCORPORA=[",1)[0]
ns={"__name__":"kephir_exp75_lib"}
exec(compile(prefix,"exp75_lazy_wx_fingerprint.py","exec"),ns)
kencode=ns["encode"]; kdecode=ns["decode"]

logical_bytes=sum(len(blob_bytes(p)) for p in FILES)
exts=collections.Counter((p.suffix.lower() or "<none>") for p in FILES)
sizes=sorted(((len(blob_bytes(p)),str(p)) for p in FILES),reverse=True)

solid_dir=OUT/"solid"; solid_dir.mkdir(exist_ok=True)
tar_path=solid_dir/"tracked_repo.tar"
make_deterministic_tar(FILES,tar_path)
tar_bytes=tar_path.stat().st_size

# KEPHIR solid, cold-start model.
kmodel={}
karc=solid_dir/"KEPHIR-EXP75"/"archive.k75"
kdec=solid_dir/"KEPHIR-EXP75"/"decoded.tar"
ktmp=solid_dir/"KEPHIR-EXP75"/"tmp"
karc.parent.mkdir(parents=True,exist_ok=True); ktmp.mkdir(exist_ok=True)
t=time.perf_counter()
kret=kencode(tar_path,karc,ktmp,kmodel)
kct=time.perf_counter()-t
t=time.perf_counter(); kdecode(karc,kdec,ktmp); kdt=time.perf_counter()-t
kok=sha256_file(tar_path)==sha256_file(kdec)
if not kok: raise RuntimeError("KEPHIR solid SHA mismatch")
solid=[dict(name="KEPHIR-EXP75",size=karc.stat().st_size,comp_time_s=kct,dec_time_s=kdt,sha_ok=kok)]

COMPETITORS=["7z-LZMA2","ZIP-Deflate","XZ-LZMA2","Zstd-19","Brotli-11","Bzip2-9","Gzip-9","LZ4-HC"]
for c in COMPETITORS:
    solid.append(competitor_solid(c,tar_path))

for r in solid:
    r["ratio_vs_tar"]=r["size"]/tar_bytes if tar_bytes else 0
    r["ratio_vs_logical"]=r["size"]/logical_bytes if logical_bytes else 0
    r["comp_MBps"]=logical_bytes/1e6/r["comp_time_s"] if r["comp_time_s"] else 0
    r["dec_MBps"]=logical_bytes/1e6/r["dec_time_s"] if r["dec_time_s"] else 0

# File-by-file aggregate. All tools receive exactly the Git blob bytes in a stable payload filename.
perfile={name:dict(name=name,size=0,comp_time_s=0.0,dec_time_s=0.0,files=0,sha_ok=True) for name in ["KEPHIR-EXP75"]+COMPETITORS}
session_model={}
pfroot=OUT/"per_file"; pfroot.mkdir(exist_ok=True)

def stream_comp(name,src,arc,dec):
    if name=="7z-LZMA2":
        arc=arc.with_suffix(".7z")
        ct=timed(["7z","a","-bd","-y","-t7z","-mx=9","-m0=lzma2","-mmt=on",str(arc),str(src)])
        dt=timed(["7z","e","-so",str(arc)],stdout_path=dec)
    elif name=="ZIP-Deflate":
        arc=arc.with_suffix(".zip")
        ct=timed(["zip","-q","-9","-j",str(arc),str(src)])
        dt=timed(["unzip","-p",str(arc)],stdout_path=dec)
    elif name=="XZ-LZMA2":
        ct=timed(["xz","-9","-T0","-c",str(src)],stdout_path=arc)
        dt=timed(["xz","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Zstd-19":
        ct=timed(["zstd","-19","-T0","-q","-c",str(src)],stdout_path=arc)
        dt=timed(["zstd","-d","-q","-c",str(arc)],stdout_path=dec)
    elif name=="Brotli-11":
        ct=timed(["brotli","-q","11","-c",str(src)],stdout_path=arc)
        dt=timed(["brotli","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Bzip2-9":
        ct=timed(["bzip2","-9","-c",str(src)],stdout_path=arc)
        dt=timed(["bzip2","-d","-c",str(arc)],stdout_path=dec)
    elif name=="Gzip-9":
        ct=timed(["gzip","-n","-9","-c",str(src)],stdout_path=arc)
        dt=timed(["gzip","-d","-c",str(arc)],stdout_path=dec)
    elif name=="LZ4-HC":
        ct=timed(["lz4","-9","-q",str(src),str(arc)])
        dt=timed(["lz4","-d","-q",str(arc),str(dec)])
    else: raise ValueError(name)
    return arc,ct,dt

payload=pfroot/"payload"
for idx,p in enumerate(FILES):
    data=blob_bytes(p); payload.write_bytes(data)
    expected=sha256_bytes(data)

    # KEPHIR current directory-session behavior: persistent learner model across files.
    kd=pfroot/"kephir"; kd.mkdir(exist_ok=True)
    ka=kd/f"{idx}.k75"; ko=kd/f"{idx}.out"; kt=kd/"tmp"; kt.mkdir(exist_ok=True)
    t=time.perf_counter(); kencode(payload,ka,kt,session_model); ct=time.perf_counter()-t
    t=time.perf_counter(); kdecode(ka,ko,kt); dt=time.perf_counter()-t
    ok=sha256_file(ko)==expected
    rr=perfile["KEPHIR-EXP75"]; rr["size"]+=ka.stat().st_size; rr["comp_time_s"]+=ct; rr["dec_time_s"]+=dt; rr["files"]+=1; rr["sha_ok"] &= ok
    if not ok: raise RuntimeError("KEPHIR per-file SHA mismatch "+str(p))
    ko.unlink()

    for name in COMPETITORS:
        d=pfroot/name.replace("/","_"); d.mkdir(exist_ok=True)
        arc=d/f"{idx}.arc"; dec=d/f"{idx}.out"
        realarc,ct,dt=stream_comp(name,payload,arc,dec)
        ok=sha256_file(dec)==expected
        rr=perfile[name]; rr["size"]+=realarc.stat().st_size; rr["comp_time_s"]+=ct; rr["dec_time_s"]+=dt; rr["files"]+=1; rr["sha_ok"] &= ok
        if not ok: raise RuntimeError(name+" per-file SHA mismatch "+str(p))
        dec.unlink()

payload.unlink(missing_ok=True)
perfile_rows=list(perfile.values())
for r in perfile_rows:
    r["ratio_vs_logical"]=r["size"]/logical_bytes if logical_bytes else 0
    r["comp_MBps"]=logical_bytes/1e6/r["comp_time_s"] if r["comp_time_s"] else 0
    r["dec_MBps"]=logical_bytes/1e6/r["dec_time_s"] if r["dec_time_s"] else 0

solid.sort(key=lambda x:x["size"])
perfile_rows.sort(key=lambda x:x["size"])

result={
  "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
  "tracked_files":len(FILES),
  "logical_bytes":logical_bytes,
  "deterministic_tar_bytes":tar_bytes,
  "extensions":exts.most_common(),
  "largest_files":[{"path":p,"bytes":n} for n,p in sizes[:20]],
  "solid":solid,
  "per_file":perfile_rows,
}
Path("realworld_repo_benchmark.json").write_text(json.dumps(result,indent=2))

def fmt_table(rows,ratio_key):
    lines=["| Compressor | Size (B) | Ratio | Comp s | Dec s | Comp MB/s | SHA |","|---|---:|---:|---:|---:|---:|:---:|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['size']:,} | {r[ratio_key]*100:.3f}% | {r['comp_time_s']:.4f} | {r['dec_time_s']:.4f} | {r['comp_MBps']:.2f} | {'PASS' if r['sha_ok'] else 'FAIL'} |")
    return "\n".join(lines)

md=[
"# KEPHIR real-world GitHub repository benchmark",
"",
f"- Commit: \`{result['git_commit']}\`",
f"- Tracked files: **{len(FILES)}**",
f"- Logical Git blob bytes: **{logical_bytes:,} B**",
f"- Deterministic TAR input: **{tar_bytes:,} B**",
"",
"## Solid repository archive",
"",
"Every compressor receives the exact same deterministic TAR stream. Ratio below is against logical Git file bytes.",
"",
fmt_table(solid,"ratio_vs_logical"),
"",
"## File-by-file aggregate",
"",
"Every tracked Git blob is compressed independently; KEPHIR keeps its session learner across the directory pass.",
"",
fmt_table(perfile_rows,"ratio_vs_logical"),
"",
"## Dataset notes",
"",
"The dataset contains only files returned by \`git ls-files\`. The .git database, downloaded corpora, compiler outputs, caches and CI artifacts are excluded.",
]
Path("realworld_repo_benchmark.md").write_text("\n".join(md))
print("REALWORLD_RESULT",json.dumps(result,sort_keys=True),flush=True)
