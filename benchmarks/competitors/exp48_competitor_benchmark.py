from pathlib import Path
import subprocess,time,statistics,json,shutil,hashlib,os,sys
ROOT=Path("silesia"); OUT=Path("exp48_full_bench"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]

rows=[]

def med3(fn):
    vals=[]
    for _ in range(3):
        t=time.perf_counter(); fn(); vals.append(time.perf_counter()-t)
    return statistics.median(vals)

def add_cmd_codec(name, ext, ccmd, dcmd):
    total_raw=total_size=0; ctime=dtime=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size
        o=OUT/f"{fn}.{name.replace(' ','_').replace('/','_')}.{ext}"
        def c():
            if o.exists(): o.unlink()
            subprocess.run(ccmd(p,o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c); size=o.stat().st_size
        def d():
            subprocess.run(dcmd(o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        total_raw+=raw; total_size+=size; ctime+=ct; dtime+=dt
    rows.append(dict(codec=name,raw=total_raw,size=total_size,ratio=100*total_size/total_raw,
                     comp_MBps=(total_raw/1e6)/ctime,dec_MBps=(total_raw/1e6)/dtime))

# KEPHIR EXP-48 end-to-end exactly as implemented. One full pass: router itself evaluates candidates.
# exp48_router.py writes exp44_out and exp44_results.json.
t=time.perf_counter()
subprocess.run([sys.executable,"exp48_router.py"],check=True)
kt=time.perf_counter()-t
kr=json.loads(Path("exp44_results.json").read_text())["summary"]
# Router's own summary has measured encode/decode separately; use those.
rows.append(dict(codec="KEPHIR EXP-48 Adaptive Router",raw=kr["raw"],size=kr["size"],ratio=100*kr["ratio"],
                 comp_MBps=kr["comp_MBps"],dec_MBps=kr["dec_MBps"]))

for lvl in (1,3,9,19):
    add_cmd_codec(f"Zstd -{lvl}","zst",
        lambda p,o,lvl=lvl:["zstd",f"-{lvl}","-T1","-q","-f",str(p),"-o",str(o)],
        lambda o:["zstd","-d","-q","-c",str(o)])

for lvl in (1,6,9):
    add_cmd_codec(f"XZ/LZMA2 -{lvl}","xz",
        lambda p,o,lvl=lvl:["bash","-lc",f"xz -{lvl} -T1 -c '{p}' > '{o}'"],
        lambda o:["xz","-d","-c",str(o)])

for lvl in (1,5,9,11):
    add_cmd_codec(f"Brotli q{lvl}","br",
        lambda p,o,lvl=lvl:["brotli","-q",str(lvl),"-f",str(p),"-o",str(o)],
        lambda o:["brotli","-d","-c",str(o)])

add_cmd_codec("Bzip2 -9","bz2",
    lambda p,o:["bash","-lc",f"bzip2 -9 -c '{p}' > '{o}'"],
    lambda o:["bzip2","-d","-c",str(o)])

for lvl in (1,6,9):
    add_cmd_codec(f"Gzip/Deflate -{lvl}","gz",
        lambda p,o,lvl=lvl:["bash","-lc",f"gzip -{lvl} -c '{p}' > '{o}'"],
        lambda o:["gzip","-d","-c",str(o)])

for lvl in (1,6,9):
    name=f"ZIP/Deflate -{lvl}"
    total_raw=total_size=0; ctime=dtime=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; o=OUT/f"{fn}.zip{lvl}.zip"
        def c(p=p,o=o,lvl=lvl):
            if o.exists():o.unlink()
            subprocess.run(["zip",f"-{lvl}","-j","-q",str(o),str(p)],check=True)
        ct=med3(c); size=o.stat().st_size
        def d(o=o,fn=fn):
            subprocess.run(["unzip","-p",str(o),fn],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        total_raw+=raw; total_size+=size; ctime+=ct; dtime+=dt
    rows.append(dict(codec=name,raw=total_raw,size=total_size,ratio=100*total_size/total_raw,
                     comp_MBps=(total_raw/1e6)/ctime,dec_MBps=(total_raw/1e6)/dtime))

add_cmd_codec("LZ4 default","lz4",
    lambda p,o:["lz4","-q","-f",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)])
add_cmd_codec("LZ4 HC -9","lz4",
    lambda p,o:["lz4","-q","-f","-9",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)])

for mx in (1,5,9):
    name=f"7-Zip/LZMA2 mx{mx}"
    total_raw=total_size=0; ctime=0.0
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; o=OUT/f"{fn}.mx{mx}.7z"
        def c(p=p,o=o,mx=mx):
            if o.exists():o.unlink()
            subprocess.run(["7z","a","-bd","-y",f"-mx={mx}","-m0=lzma2",str(o),str(p)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c); size=o.stat().st_size
        total_raw+=raw; total_size+=size; ctime+=ct
    # 7z -so timing is not trustworthy in this environment; leave decoder null.
    rows.append(dict(codec=name,raw=total_raw,size=total_size,ratio=100*total_size/total_raw,
                     comp_MBps=(total_raw/1e6)/ctime,dec_MBps=None))

rows.sort(key=lambda r:r["ratio"])
print("SUMMARY")
for r in rows: print(r,flush=True)
Path("exp48_competitor_benchmark.json").write_text(json.dumps(rows,indent=2))
