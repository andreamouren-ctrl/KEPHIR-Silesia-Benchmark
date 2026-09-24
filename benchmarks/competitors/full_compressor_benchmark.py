from pathlib import Path
import subprocess,time,statistics,hashlib,json,shutil,os
ROOT=Path("silesia"); OUT=Path("full_bench_out"); OUT.mkdir(exist_ok=True)
FILES=["dickens","mozilla","mr","nci","ooffice","osdb","reymont","samba","sao","webster","x-ray","xml"]

def med3(fn):
    vals=[]
    for _ in range(3):
        t=time.perf_counter(); fn(); vals.append(time.perf_counter()-t)
    return statistics.median(vals)

rows=[]

def add_cmd_codec(name, ext, ccmd, dcmd):
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; o=OUT/f"{fn}.{name.replace(' ','_').replace('/','_')}.{ext}"
        def c():
            if o.exists(): o.unlink()
            subprocess.run(ccmd(p,o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c); size=o.stat().st_size
        def d():
            subprocess.run(dcmd(o),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        rows.append(dict(file=fn,codec=name,raw=raw,size=size,ratio=100*size/raw,
                         comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt))

# KEPHIR 1t and 6t
for threads in (1,6):
    name=f"KEPHIR EXP-27A {threads}t"
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; arc=OUT/f"k{threads}_{fn}.aur"
        def c():
            if arc.exists(): arc.unlink()
            subprocess.run(["./kephir27","cp",str(p),str(arc),str(threads),"6.55","9.42","1.20"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c); size=arc.stat().st_size
        dec=OUT/f"k{threads}_dec_{fn}"
        def d():
            if dec.exists(): shutil.rmtree(dec)
            subprocess.run(["./kephir27","dp",str(arc),str(dec),str(threads)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        ok=hashlib.sha256((dec/fn).read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
        if not ok: raise SystemExit("KEPHIR SHA FAIL "+fn)
        rows.append(dict(file=fn,codec=name,raw=raw,size=size,ratio=100*size/raw,
                         comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt))

# zstd
for lvl in (1,3,9,19):
    add_cmd_codec(f"Zstd -{lvl}","zst",
        lambda p,o,lvl=lvl:["zstd",f"-{lvl}","-T1","-q","-f",str(p),"-o",str(o)],
        lambda o:["zstd","-d","-q","-c",str(o)])

# xz/lzma2
for lvl in (1,6,9):
    add_cmd_codec(f"XZ/LZMA2 -{lvl}","xz",
        lambda p,o,lvl=lvl:["bash","-lc",f"xz -{lvl} -T1 -c '{p}' > '{o}'"],
        lambda o:["xz","-d","-c",str(o)])

# gzip deflate
for lvl in (1,6,9):
    add_cmd_codec(f"Gzip/Deflate -{lvl}","gz",
        lambda p,o,lvl=lvl:["bash","-lc",f"gzip -{lvl} -c '{p}' > '{o}'"],
        lambda o:["gzip","-d","-c",str(o)])

# bzip2
add_cmd_codec("Bzip2 -9","bz2",
    lambda p,o:["bash","-lc",f"bzip2 -9 -c '{p}' > '{o}'"],
    lambda o:["bzip2","-d","-c",str(o)])

# brotli
for lvl in (1,5,9,11):
    add_cmd_codec(f"Brotli q{lvl}","br",
        lambda p,o,lvl=lvl:["brotli",f"-q",str(lvl),"-f",str(p),"-o",str(o)],
        lambda o:["brotli","-d","-c",str(o)])

# lz4
add_cmd_codec("LZ4 default","lz4",
    lambda p,o:["lz4","-q","-f",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)])
add_cmd_codec("LZ4 HC -9","lz4",
    lambda p,o:["lz4","-q","-f","-9",str(p),str(o)],
    lambda o:["lz4","-d","-q","-c",str(o)])

# 7-Zip LZMA2; archive one file, extract to stdout
for mx in (1,5,9):
    name=f"7-Zip/LZMA2 mx{mx}"
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; o=OUT/f"{fn}.mx{mx}.7z"
        def c(p=p,o=o,mx=mx):
            if o.exists(): o.unlink()
            subprocess.run(["7z","a","-bd","-y",f"-mx={mx}","-m0=lzma2",str(o),str(p)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ct=med3(c); size=o.stat().st_size
        def d(o=o,fn=fn):
            subprocess.run(["7z","x","-so",str(o),fn],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        rows.append(dict(file=fn,codec=name,raw=raw,size=size,ratio=100*size/raw,
                         comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt))

# ZIP deflate
for lvl in (1,6,9):
    name=f"ZIP/Deflate -{lvl}"
    for fn in FILES:
        p=ROOT/fn; raw=p.stat().st_size; o=OUT/f"{fn}.zip{lvl}.zip"
        def c(p=p,o=o,lvl=lvl):
            if o.exists(): o.unlink()
            subprocess.run(["zip",f"-{lvl}","-j","-q",str(o),str(p)],check=True)
        ct=med3(c); size=o.stat().st_size
        def d(o=o,fn=fn):
            subprocess.run(["unzip","-p",str(o),fn],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dt=med3(d)
        rows.append(dict(file=fn,codec=name,raw=raw,size=size,ratio=100*size/raw,
                         comp_MBps=raw/1e6/ct,dec_MBps=raw/1e6/dt))

# aggregate weighted harmonic by bytes/time
summary=[]
for codec in sorted(set(r["codec"] for r in rows)):
    rr=[r for r in rows if r["codec"]==codec]
    raw=sum(r["raw"] for r in rr); size=sum(r["size"] for r in rr)
    ct=sum(r["raw"]/1e6/r["comp_MBps"] for r in rr)
    dt=sum(r["raw"]/1e6/r["dec_MBps"] for r in rr)
    summary.append(dict(codec=codec,raw=raw,size=size,ratio=100*size/raw,
                        comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt))
summary.sort(key=lambda x:x["ratio"])

arch={
"KEPHIR EXP-27A 1t":"LZ match parser + adaptive residual/probability model + arithmetic/range coding + 3D/4D prediction",
"KEPHIR EXP-27A 6t":"LZ match parser + adaptive residual/probability model + arithmetic/range coding + 3D/4D prediction",
"Zstd -1":"LZ77 + FSE/tANS + Huffman",
"Zstd -3":"LZ77 + FSE/tANS + Huffman",
"Zstd -9":"LZ77 + FSE/tANS + Huffman",
"Zstd -19":"LZ77 + FSE/tANS + Huffman",
"XZ/LZMA2 -1":"LZ77/LZMA2 + range coder + context models",
"XZ/LZMA2 -6":"LZ77/LZMA2 + range coder + context models",
"XZ/LZMA2 -9":"LZ77/LZMA2 + range coder + context models",
"Gzip/Deflate -1":"LZ77 + Huffman",
"Gzip/Deflate -6":"LZ77 + Huffman",
"Gzip/Deflate -9":"LZ77 + Huffman",
"ZIP/Deflate -1":"LZ77 + Huffman",
"ZIP/Deflate -6":"LZ77 + Huffman",
"ZIP/Deflate -9":"LZ77 + Huffman",
"Bzip2 -9":"BWT + MTF + Huffman",
"Brotli q1":"LZ77 + context modeling + Huffman",
"Brotli q5":"LZ77 + context modeling + Huffman",
"Brotli q9":"LZ77 + context modeling + Huffman",
"Brotli q11":"LZ77 + context modeling + Huffman",
"LZ4 default":"LZ77-family fast match coding",
"LZ4 HC -9":"LZ77-family high-compression parser",
"7-Zip/LZMA2 mx1":"LZMA2 + range coder + context models",
"7-Zip/LZMA2 mx5":"LZMA2 + range coder + context models",
"7-Zip/LZMA2 mx9":"LZMA2 + range coder + context models",
}
for r in summary: r["architecture"]=arch.get(r["codec"],"")
Path("full_benchmark_results.json").write_text(json.dumps({"summary":summary,"rows":rows},indent=2))
md=["# KEPHIR EXP-27A — Extended Silesia benchmark","",
"| Codec | Size | Ratio % | Comp MB/s | Dec MB/s | Architecture |",
"|---|---:|---:|---:|---:|---|"]
for r in summary:
    md.append(f'| {r["codec"]} | {r["size"]:,} | {r["ratio"]:.3f} | {r["comp_MBps"]:.1f} | {r["dec_MBps"]:.1f} | {r["architecture"]} |')
Path("FULL_BENCHMARK.md").write_text("\n".join(md))
print("\n".join(md))
