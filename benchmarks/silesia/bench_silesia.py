from pathlib import Path
import subprocess, time, statistics, hashlib, csv, json, shutil
import brotli, lz4.frame

ROOT=Path("silesia")
OUT=Path("bench_out")
OUT.mkdir(exist_ok=True)
KEPHIR="./kephir22"
files=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]

def median3(fn):
    vals=[]
    for _ in range(3):
        t=time.perf_counter(); fn(); vals.append(time.perf_counter()-t)
    return statistics.median(vals)

rows=[]
for name in files:
    p=ROOT/name
    raw=p.stat().st_size
    data=p.read_bytes()

    arc=OUT/f"{name}.aur"
    def kc():
        if arc.exists(): arc.unlink()
        subprocess.run([KEPHIR,"cp",str(p),str(arc),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    kct=median3(kc)
    ksize=arc.stat().st_size

    kout=OUT/f"k_{name}"
    def kd():
        if kout.exists(): shutil.rmtree(kout)
        subprocess.run([KEPHIR,"dp",str(arc),str(kout),"6"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    kdt=median3(kd)
    restored=(kout/name).read_bytes()
    assert hashlib.sha256(restored).digest()==hashlib.sha256(data).digest()
    rows.append(dict(file=name,codec="KEPHIR EXP-22",raw=raw,size=ksize,ratio=100*ksize/raw,comp_MBps=raw/1e6/kct,dec_MBps=raw/1e6/kdt))

    for codec,ext,ccmd,dcmd in [
        ("Zstd -1","zst",lambda o:["zstd","-1","-q","-f",str(p),"-o",str(o)],lambda o:["zstd","-d","-q","-c",str(o)]),
        ("Zstd -3","zst",lambda o:["zstd","-3","-q","-f",str(p),"-o",str(o)],lambda o:["zstd","-d","-q","-c",str(o)]),
        ("Zstd -9","zst",lambda o:["zstd","-9","-q","-f",str(p),"-o",str(o)],lambda o:["zstd","-d","-q","-c",str(o)]),
        ("XZ -1","xz",lambda o:["bash","-lc",f"xz -1 -T1 -c '{p}' > '{o}'"],lambda o:["xz","-d","-c",str(o)]),
        ("XZ -6","xz",lambda o:["bash","-lc",f"xz -6 -T1 -c '{p}' > '{o}'"],lambda o:["xz","-d","-c",str(o)]),
        ("Gzip -6","gz",lambda o:["bash","-lc",f"gzip -6 -c '{p}' > '{o}'"],lambda o:["gzip","-d","-c",str(o)]),
        ("Bzip2 -9","bz2",lambda o:["bash","-lc",f"bzip2 -9 -c '{p}' > '{o}'"],lambda o:["bzip2","-d","-c",str(o)]),
    ]:
        o=OUT/f"{name}.{codec.replace(' ','_').replace('/','_')}.{ext}"
        def c():
            if o.exists(): o.unlink()
            subprocess.run(ccmd(o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=median3(c); size=o.stat().st_size
        def d():
            subprocess.run(dcmd(o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=median3(d)
        rows.append(dict(file=name,codec=codec,raw=raw,size=size,ratio=100*size/raw,comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt))

    btimes=[]
    for _ in range(3):
        t=time.perf_counter(); blob=brotli.compress(data,quality=5); btimes.append(time.perf_counter()-t)
    dbtimes=[]
    for _ in range(3):
        t=time.perf_counter(); dec=brotli.decompress(blob); dbtimes.append(time.perf_counter()-t)
    assert dec==data
    rows.append(dict(file=name,codec="Brotli q5",raw=raw,size=len(blob),ratio=100*len(blob)/raw,comp_MBps=raw/1e6/statistics.median(btimes),dec_MBps=raw/1e6/statistics.median(dbtimes)))

    ltimes=[]
    for _ in range(3):
        t=time.perf_counter(); lblob=lz4.frame.compress(data); ltimes.append(time.perf_counter()-t)
    ldt=[]
    for _ in range(3):
        t=time.perf_counter(); ldec=lz4.frame.decompress(lblob); ldt.append(time.perf_counter()-t)
    assert ldec==data
    rows.append(dict(file=name,codec="LZ4 default",raw=raw,size=len(lblob),ratio=100*len(lblob)/raw,comp_MBps=raw/1e6/statistics.median(ltimes),dec_MBps=raw/1e6/statistics.median(ldt)))

with open("results_silesia.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["file","codec","raw","size","ratio","comp_MBps","dec_MBps"])
    w.writeheader(); w.writerows(rows)

totals={}
for r in rows:
    t=totals.setdefault(r["codec"],{"raw":0,"size":0,"comp_weight":0.0,"dec_weight":0.0})
    t["raw"]+=r["raw"]; t["size"]+=r["size"]
    t["comp_weight"]+=r["raw"]/r["comp_MBps"]
    t["dec_weight"]+=r["raw"]/r["dec_MBps"]

summary=[]
for codec,t in totals.items():
    raw=t["raw"]
    summary.append(dict(codec=codec,raw=raw,size=t["size"],ratio=100*t["size"]/raw,comp_MBps=raw/t["comp_weight"],dec_MBps=raw/t["dec_weight"]))
summary.sort(key=lambda x:x["ratio"])

Path("results_silesia.json").write_text(json.dumps({"rows":rows,"totals":summary},indent=2))
md=["# KEPHIR EXP-22 — Silesia Benchmark","","| Codec | Total bytes | Ratio % | Comp MB/s | Decomp MB/s |","|---|---:|---:|---:|---:|"]
for r in summary:
    md.append(f'| {r["codec"]} | {r["size"]:,} | {r["ratio"]:.3f} | {r["comp_MBps"]:.1f} | {r["dec_MBps"]:.1f} |')
Path("RESULTS.md").write_text("\n".join(md))
print("\n".join(md))
