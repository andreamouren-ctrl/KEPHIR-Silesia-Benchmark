from pathlib import Path
import subprocess,time,statistics,json,shutil,hashlib,sys

ROOT=Path("silesia")
OUT=Path("exp56_full_bench")
OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]
RAW_TOTAL=sum((ROOT/f).stat().st_size for f in FILES)

rows=[]

def med3(fn):
    vals=[]
    for _ in range(3):
        t=time.perf_counter()
        fn()
        vals.append(time.perf_counter()-t)
    return statistics.median(vals)

def add_row(codec, family, profile, raw, size, ctime, dtime):
    rows.append(dict(
        codec=codec,
        type=family,
        profile=profile,
        raw=raw,
        size=size,
        ratio_pct=100.0*size/raw,
        comp_time_s=ctime,
        dec_time_s=dtime,
        comp_MBps=(raw/1e6)/ctime if ctime else None,
        dec_MBps=(raw/1e6)/dtime if dtime else None
    ))

def add_cmd_codec(name, family, profile, ext, ccmd, dcmd):
    total_raw=total_size=0
    ctime=dtime=0.0
    for fn in FILES:
        p=ROOT/fn
        raw=p.stat().st_size
        o=OUT/f"{fn}.{name.replace(' ','_').replace('/','_')}.{ext}"

        def c():
            if o.exists(): o.unlink()
            subprocess.run(ccmd(p,o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c)
        size=o.stat().st_size

        def d():
            subprocess.run(dcmd(o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)

        total_raw+=raw
        total_size+=size
        ctime+=ct
        dtime+=dt

    add_row(name,family,profile,total_raw,total_size,ctime,dtime)

# KEPHIR EXP-56: exact end-to-end ULTRA implementation.
t=time.perf_counter()
subprocess.run([sys.executable,"research/routers/exp56_ultra_adaptive_subchunk.py"],check=True)
wall=time.perf_counter()-t
kr=json.loads(Path("exp56_results.json").read_text())["summary"]
k_ct=(kr["raw"]/1e6)/kr["comp_MBps"]
k_dt=(kr["raw"]/1e6)/kr["dec_MBps"]
add_row(
    "KEPHIR EXP-56 Adaptive Subchunk",
    "Multi-backend predictive LZ + arithmetic/range-style entropy coding + structural transforms + adaptive subchunks",
    "Ultra",
    kr["raw"],kr["size"],k_ct,k_dt
)

for lvl,profile in ((1,"Rapido"),(3,"Medio"),(9,"Medio"),(19,"Ultra")):
    add_cmd_codec(
        f"Zstd -{lvl}","LZ77 + FSE/Huffman",profile,"zst",
        lambda p,o,lvl=lvl:["zstd",f"-{lvl}","-T1","-q","-f",str(p),"-o",str(o)],
        lambda o:["zstd","-d","-q","-c",str(o)]
    )

for lvl,profile in ((1,"Rapido"),(6,"Medio"),(9,"Ultra")):
    add_cmd_codec(
        f"XZ/LZMA2 -{lvl}","LZMA2 + range coding",profile,"xz",
        lambda p,o,lvl=lvl:["bash","-lc",f"xz -{lvl} -T1 -c '{p}' > '{o}'"],
        lambda o:["xz","-d","-c",str(o)]
    )

for lvl,profile in ((1,"Rapido"),(5,"Medio"),(9,"Ultra"),(11,"Ultra")):
    add_cmd_codec(
        f"Brotli q{lvl}","LZ77 + context modeling + Huffman",profile,"br",
        lambda p,o,lvl=lvl:["brotli","-q",str(lvl),"-f",str(p),"-o",str(o)],
        lambda o:["brotli","-d","-c",str(o)]
    )

add_cmd_codec(
    "Bzip2 -9","BWT + MTF + Huffman","Ultra","bz2",
    lambda p,o:["bash","-lc",f"bzip2 -9 -c '{p}' > '{o}'"],
    lambda o:["bzip2","-d","-c",str(o)]
)

for lvl,profile in ((1,"Rapido"),(6,"Medio"),(9,"Ultra")):
    add_cmd_codec(
        f"Gzip/Deflate -{lvl}","LZ77 + Huffman (Deflate)",profile,"gz",
        lambda p,o,lvl=lvl:["bash","-lc",f"gzip -{lvl} -c '{p}' > '{o}'"],
        lambda o:["gzip","-d","-c",str(o)]
    )

for lvl,profile in ((1,"Rapido"),(6,"Medio"),(9,"Ultra")):
    name=f"ZIP/Deflate -{lvl}"
    total_raw=total_size=0
    ctime=dtime=0.0
    for fn in FILES:
        p=ROOT/fn
        raw=p.stat().st_size
        o=OUT/f"{fn}.zip{lvl}.zip"
        def c(p=p,o=o,lvl=lvl):
            if o.exists(): o.unlink()
            subprocess.run(["zip",f"-{lvl}","-j","-q",str(o),str(p)],check=True)
        ct=med3(c)
        size=o.stat().st_size
        def d(o=o,fn=fn):
            subprocess.run(["unzip","-p",str(o),fn],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        total_raw+=raw; total_size+=size; ctime+=ct; dtime+=dt
    add_row(name,"Deflate in ZIP container",profile,total_raw,total_size,ctime,dtime)

add_cmd_codec(
    "LZ4 default","LZ77-family fast match coding","Rapido","lz4",
    lambda p,o:["lz4","-q","-f",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)]
)
add_cmd_codec(
    "LZ4 HC -9","LZ77-family high-compression parser","Ultra","lz4",
    lambda p,o:["lz4","-q","-f","-9",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)]
)

for mx,profile in ((1,"Rapido"),(5,"Medio"),(9,"Ultra")):
    name=f"7-Zip/LZMA2 mx{mx}"
    total_raw=total_size=0
    ctime=dtime=0.0
    for fn in FILES:
        p=ROOT/fn
        raw=p.stat().st_size
        o=OUT/f"{fn}.mx{mx}.7z"
        def c(p=p,o=o,mx=mx):
            if o.exists(): o.unlink()
            subprocess.run(["7z","a","-bd","-y",f"-mx={mx}","-m0=lzma2",str(o),str(p)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c)
        size=o.stat().st_size

        extract_dir=OUT/f"x_{fn}_{mx}"
        def d(o=o,extract_dir=extract_dir):
            if extract_dir.exists(): shutil.rmtree(extract_dir)
            extract_dir.mkdir()
            subprocess.run(["7z","x","-bd","-y",f"-o{extract_dir}",str(o)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            shutil.rmtree(extract_dir)
        dt=med3(d)

        total_raw+=raw; total_size+=size; ctime+=ct; dtime+=dt
    add_row(name,"LZMA2 + range coding in 7z container",profile,total_raw,total_size,ctime,dtime)

rows.sort(key=lambda r:r["ratio_pct"])
print("SUMMARY")
for r in rows:
    print(json.dumps(r),flush=True)

Path("exp56_competitor_benchmark.json").write_text(json.dumps({
    "corpus":"Silesia",
    "raw_total":RAW_TOTAL,
    "timing":"median of 3 runs per corpus file for competitors; EXP-56 native measured end-to-end timing",
    "rows":rows
},indent=2))
