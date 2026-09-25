#!/usr/bin/env python3
from pathlib import Path
import subprocess, shutil, os, json, hashlib, time, tempfile

ROOT=Path.cwd()
OUT=ROOT/"kephir_final_qualification"
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def tracked_snapshot():
    dst=OUT/"repo_input";dst.mkdir()
    raw=subprocess.check_output(["git","ls-files","-z"])
    paths=[Path(x.decode()) for x in raw.split(b"\0") if x]
    for p in paths:
        q=dst/p;q.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():
            q.write_bytes(os.readlink(p).encode())
        else:
            shutil.copyfile(p,q)
    return dst

def files(root):
    return sorted([p for p in root.rglob("*") if p.is_file()],key=lambda p:p.relative_to(root).as_posix())

def logical(root):
    return sum(p.stat().st_size for p in files(root))

def putv(out,v):
    while True:
        b=v&0x7f;v>>=7
        if v:out.append(b|0x80)
        else:out.append(b);return

def make_flat(root,dst):
    out=bytearray()
    for p in files(root):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes()
        putv(out,len(rel));out.extend(rel);putv(out,len(data));out.extend(data)
    dst.write_bytes(out)

def run(cmd,stdout=None,env=None):
    t=time.perf_counter()
    if stdout:
        with open(stdout,"wb") as f:
            subprocess.run(cmd,check=True,stdout=f,stderr=subprocess.DEVNULL,env=env)
    else:
        r=subprocess.run(cmd,check=True,text=True,capture_output=True,env=env)
        return time.perf_counter()-t,r.stdout.strip()
    return time.perf_counter()-t,None

def kephir(root,label,knowledge):
    arc=OUT/f"{label}.kpf"
    dest=OUT/f"{label}_out"
    home=OUT/f"home_{label}"
    env=os.environ.copy();env["KEPHIR_HOME"]=str(home);env["KEPHIR_WORKERS"]="16"
    cmd=[sys.executable,"release/kephir_final.py","compress",str(root),str(arc),"--workers","16"]
    if knowledge=="cold":cmd.append("--cold")
    elif knowledge=="factory":cmd.append("--no-local")
    else:raise ValueError(knowledge)
    _,stdout=run(cmd,env=env)
    cr=json.loads(stdout)
    t,stdout2=run([sys.executable,"release/kephir_final.py","extract",str(arc),str(dest)],env=env)
    er=json.loads(stdout2)
    # independent file-level verification
    for p in files(root):
        q=dest/p.relative_to(root)
        if not q.exists() or sha(p)!=sha(q):raise RuntimeError("KEPHIR restore mismatch "+str(p))
    return {
      "name":f"KEPHIR-1.0-{knowledge}","archive_bytes":arc.stat().st_size,
      "ratio":arc.stat().st_size/logical(root),"comp_time_s":cr["time_s"],
      "dec_time_s":er["time_s"],"verified":True,"stats":cr.get("stats",{})
    }

def competitor(flat,raw_bytes,name):
    d=OUT/"competitors";d.mkdir(exist_ok=True)
    arc=d/(name.replace("/","_")+".bin");dec=d/(name.replace("/","_")+".dec")
    if name=="Brotli-11":
        ct,_=run(["brotli","-q","11","-c",str(flat)],stdout=arc)
        dt,_=run(["brotli","-d","-c",str(arc)],stdout=dec)
    elif name=="XZ-9":
        ct,_=run(["xz","-9","-T0","-c",str(flat)],stdout=arc)
        dt,_=run(["xz","-d","-c",str(arc)],stdout=dec)
    elif name=="7z-LZMA2":
        arc=arc.with_suffix(".7z")
        ct,_=run(["7z","a","-bd","-y","-t7z","-mx=9","-m0=lzma2","-mmt=on",str(arc),str(flat)])
        dt,_=run(["7z","e","-so",str(arc)],stdout=dec)
    elif name=="Zstd-19":
        ct,_=run(["zstd","-19","-T0","-q","-c",str(flat)],stdout=arc)
        dt,_=run(["zstd","-d","-q","-c",str(arc)],stdout=dec)
    elif name=="Bzip2-9":
        ct,_=run(["bzip2","-9","-c",str(flat)],stdout=arc)
        dt,_=run(["bzip2","-d","-c",str(arc)],stdout=dec)
    elif name=="Gzip-9":
        ct,_=run(["gzip","-n","-9","-c",str(flat)],stdout=arc)
        dt,_=run(["gzip","-d","-c",str(arc)],stdout=dec)
    elif name=="LZ4-HC":
        ct,_=run(["lz4","-9","-q",str(flat),str(arc)])
        dt,_=run(["lz4","-d","-q",str(arc),str(dec)])
    else:raise ValueError(name)
    if sha(flat)!=sha(dec):raise RuntimeError(name+" SHA fail")
    return {"name":name,"archive_bytes":arc.stat().st_size,"ratio":arc.stat().st_size/raw_bytes,
      "comp_time_s":ct,"dec_time_s":dt,"verified":True}

import sys
repo_input=tracked_snapshot()
silesia=ROOT/"corpora"/"silesia"
if not silesia.exists():raise SystemExit("Silesia dataset missing")

datasets={"repository-unseen":repo_input,"silesia-canonical":silesia}
competitors=["Brotli-11","XZ-9","7z-LZMA2","Zstd-19","Bzip2-9","Gzip-9","LZ4-HC"]
result={"version":"1.0.0-rc1","datasets":{}}

for dname,root in datasets.items():
    raw=logical(root);flat=OUT/f"{dname}.flat";make_flat(root,flat)
    rows=[]
    # Unseen repository is the fair Factory generalization test.
    rows.append(kephir(root,dname+"_cold","cold"))
    rows.append(kephir(root,dname+"_factory","factory"))
    for c in competitors:rows.append(competitor(flat,raw,dname+"-"+c) if False else {})
    # competitor helper uses name as codec key; keep dataset outputs isolated
    crows=[]
    for c in competitors:
        # rename artifact target temporarily by using per-dataset working directory
        old=OUT/"competitors"; dscomp=OUT/f"competitors_{dname}"
        if old.exists(): shutil.rmtree(old)
        r=competitor(flat,raw,c)
        if old.exists():
            if dscomp.exists():shutil.rmtree(dscomp)
            old.rename(dscomp)
        crows.append(r)
    rows=rows[:2]+crows
    for r in rows:
        r["comp_MBps"]=raw/1e6/r["comp_time_s"] if r["comp_time_s"] else 0
        r["dec_MBps"]=raw/1e6/r["dec_time_s"] if r["dec_time_s"] else 0
    result["datasets"][dname]={
      "files":len(files(root)),"logical_bytes":raw,"flat_bytes":flat.stat().st_size,
      "rows":sorted(rows,key=lambda r:r["archive_bytes"])
    }

Path("kephir_final_qualification.json").write_text(json.dumps(result,indent=2))

lines=["# KEPHIR 1.0 Final Candidate Qualification",""]
for name,d in result["datasets"].items():
    lines += [f"## {name}","",f"Files: **{d['files']}** — logical bytes: **{d['logical_bytes']:,}** — compact framed bytes: **{d['flat_bytes']:,}**","",
      "| Compressor | Bytes | Ratio | Comp s | Dec s | Comp MB/s | SHA |",
      "|---|---:|---:|---:|---:|---:|:---:|"]
    for r in d["rows"]:
        lines.append(f"| {r['name']} | {r['archive_bytes']:,} | {r['ratio']*100:.3f}% | {r['comp_time_s']:.3f} | {r['dec_time_s']:.3f} | {r['comp_MBps']:.2f} | {'PASS' if r['verified'] else 'FAIL'} |")
    lines.append("")
Path("kephir_final_qualification.md").write_text("\n".join(lines))
print("FINAL_QUALIFICATION",json.dumps(result,sort_keys=True),flush=True)
