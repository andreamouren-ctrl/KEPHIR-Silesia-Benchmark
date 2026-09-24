from pathlib import Path
import subprocess,time,json,hashlib,shutil,sys,shlex

ROOT=Path("corpora")
OUT=Path("multicorpus_bench")
OUT.mkdir(exist_ok=True)

CORPORA={
    "Silesia": ROOT/"silesia",
    "Canterbury": ROOT/"canterbury",
    "Calgary": ROOT/"calgary",
    "Canterbury-Large": ROOT/"large",
    "Artificial": ROOT/"artificial",
    "enwik8": ROOT/"enwik8",
}

# Load EXP-58 functions without executing its Silesia benchmark main block.
src=Path("research/routers/exp58_ultra_selective_verify.py").read_text()
prelude=src.split('root=Path("silesia")',1)[0]
ns={}
exec(prelude,ns)
k_encode=ns["encode"]
k_decode=ns["decode"]

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def files_for(corpus,path):
    if corpus=="enwik8":
        return [path/"enwik8"]
    return sorted(p for p in path.rglob("*") if p.is_file())

def run(cmd,stdout=None):
    return subprocess.run(cmd,check=True,stdout=stdout,stderr=subprocess.DEVNULL)

def bench_cmd_file(codec,profile,family,src,arc,compress_cmd,decompress_cmd):
    if arc.exists(): arc.unlink()
    t=time.perf_counter(); run(compress_cmd(src,arc)); ct=time.perf_counter()-t
    size=arc.stat().st_size

    dec=arc.with_suffix(arc.suffix+".dec")
    if dec.exists(): dec.unlink()
    t=time.perf_counter(); decompress_cmd(arc,dec); dt=time.perf_counter()-t
    ok=sha256_file(src)==sha256_file(dec)
    dec.unlink()
    if not ok: raise SystemExit(f"SHA FAIL {codec} {src}")

    raw=src.stat().st_size
    return dict(codec=codec,type=family,profile=profile,file=str(src.name),
                raw=raw,size=size,ratio_pct=100.0*size/raw,
                comp_time_s=ct,dec_time_s=dt,
                comp_MBps=(raw/1e6)/ct if ct else None,
                dec_MBps=(raw/1e6)/dt if dt else None,
                sha_ok=True)

def stdout_decompress(cmd_builder):
    def d(arc,dec):
        with open(dec,"wb") as o:
            run(cmd_builder(arc),stdout=o)
    return d

CODECS=[]
def add(codec,family,profile,ext,c,d):
    CODECS.append((codec,family,profile,ext,c,d))

for lvl,profile in ((1,"Rapido"),(3,"Medio"),(9,"Medio"),(19,"Ultra")):
    add(f"Zstd -{lvl}","LZ77 + FSE/Huffman",profile,"zst",
        lambda p,o,lvl=lvl:["zstd",f"-{lvl}","-T1","-q","-f",str(p),"-o",str(o)],
        stdout_decompress(lambda o:["zstd","-d","-q","-c",str(o)]))

for lvl,profile in ((1,"Rapido"),(6,"Medio"),(9,"Ultra")):
    add(f"XZ/LZMA2 -{lvl}","LZMA2 + range coding",profile,"xz",
        lambda p,o,lvl=lvl:["bash","-lc",f"xz -{lvl} -T1 -c {shlex.quote(str(p))} > {shlex.quote(str(o))}"],
        stdout_decompress(lambda o:["xz","-d","-c",str(o)]))

for lvl,profile in ((1,"Rapido"),(5,"Medio"),(9,"Ultra"),(11,"Ultra")):
    add(f"Brotli q{lvl}","LZ77 + context modeling + Huffman",profile,"br",
        lambda p,o,lvl=lvl:["brotli","-q",str(lvl),"-f",str(p),"-o",str(o)],
        stdout_decompress(lambda o:["brotli","-d","-c",str(o)]))

add("Bzip2 -9","BWT + MTF + Huffman","Ultra","bz2",
    lambda p,o:["bash","-lc",f"bzip2 -9 -c {shlex.quote(str(p))} > {shlex.quote(str(o))}"],
    stdout_decompress(lambda o:["bzip2","-d","-c",str(o)]))

for lvl,profile in ((1,"Rapido"),(6,"Medio"),(9,"Ultra")):
    add(f"Gzip/Deflate -{lvl}","LZ77 + Huffman (Deflate)",profile,"gz",
        lambda p,o,lvl=lvl:["bash","-lc",f"gzip -{lvl} -c {shlex.quote(str(p))} > {shlex.quote(str(o))}"],
        stdout_decompress(lambda o:["gzip","-d","-c",str(o)]))

add("LZ4 default","LZ77-family fast match coding","Rapido","lz4",
    lambda p,o:["lz4","-q","-f",str(p),str(o)],
    stdout_decompress(lambda o:["lz4","-d","-q","-c",str(o)]))
add("LZ4 HC -9","LZ77-family high-compression parser","Ultra","lz4",
    lambda p,o:["lz4","-q","-f","-9",str(p),str(o)],
    stdout_decompress(lambda o:["lz4","-d","-q","-c",str(o)]))

rows=[]
for corpus,cpath in CORPORA.items():
    files=files_for(corpus,cpath)
    if not files: raise SystemExit(f"EMPTY CORPUS {corpus} {cpath}")
    print(f"CORPUS {corpus} files={len(files)}",flush=True)

    # KEPHIR EXP-58
    for idx,p in enumerate(files):
        tmp=OUT/f"tmp_k_{corpus}_{idx}"
        tmp.mkdir(exist_ok=True)
        arc=OUT/f"k_{corpus}_{idx}.k58";dec=OUT/f"k_{corpus}_{idx}.dec"
        t=time.perf_counter(); k_encode(p,arc,tmp); ct=time.perf_counter()-t
        t=time.perf_counter(); k_decode(arc,dec,tmp); dt=time.perf_counter()-t
        ok=sha256_file(p)==sha256_file(dec)
        if not ok: raise SystemExit(f"SHA FAIL KEPHIR {p}")
        raw=p.stat().st_size;size=arc.stat().st_size
        rows.append(dict(corpus=corpus,codec="KEPHIR EXP-58",type="Predictive LZ + entropy coding + adaptive transforms/subchunks",
                         profile="Ultra",file=p.name,raw=raw,size=size,ratio_pct=100.0*size/raw,
                         comp_time_s=ct,dec_time_s=dt,comp_MBps=(raw/1e6)/ct,dec_MBps=(raw/1e6)/dt,sha_ok=True))
        dec.unlink();shutil.rmtree(tmp)

    # Command-line competitors.
    for codec,family,profile,ext,ccmd,dcmd in CODECS:
        for idx,p in enumerate(files):
            safe=codec.replace(" ","_").replace("/","_")
            arc=OUT/f"{corpus}_{idx}_{safe}.{ext}"
            r=bench_cmd_file(codec,profile,family,p,arc,ccmd,dcmd)
            r["corpus"]=corpus
            rows.append(r)

    # 7-Zip separately because decompression needs extraction.
    for mx,profile in ((1,"Rapido"),(5,"Medio"),(9,"Ultra")):
        codec=f"7-Zip/LZMA2 mx{mx}"
        for idx,p in enumerate(files):
            arc=OUT/f"{corpus}_{idx}_7z_mx{mx}.7z"
            if arc.exists():arc.unlink()
            t=time.perf_counter()
            run(["7z","a","-bd","-y",f"-mx={mx}","-m0=lzma2",str(arc),str(p)])
            ct=time.perf_counter()-t
            size=arc.stat().st_size
            dec=OUT/f"{corpus}_{idx}_7z_mx{mx}.dec"
            if dec.exists(): dec.unlink()
            t=time.perf_counter()
            with open(dec,"wb") as o:
                run(["7z","x","-so",str(arc)],stdout=o)
            dt=time.perf_counter()-t
            if sha256_file(p)!=sha256_file(dec):
                raise SystemExit(f"SHA FAIL {codec} {p}")
            dec.unlink()
            raw=p.stat().st_size
            rows.append(dict(corpus=corpus,codec=codec,type="LZMA2 + range coding in 7z container",
                             profile=profile,file=p.name,raw=raw,size=size,ratio_pct=100.0*size/raw,
                             comp_time_s=ct,dec_time_s=dt,comp_MBps=(raw/1e6)/ct,
                             dec_MBps=(raw/1e6)/dt,sha_ok=True))

# Aggregate only corpora where aggregation is meaningful; Artificial and Large
# are still provided but explicitly marked non-canonical aggregate.
summary=[]
for corpus in CORPORA:
    codecs=sorted(set(r["codec"] for r in rows if r["corpus"]==corpus))
    for codec in codecs:
        rr=[r for r in rows if r["corpus"]==corpus and r["codec"]==codec]
        raw=sum(r["raw"] for r in rr);size=sum(r["size"] for r in rr)
        ct=sum(r["comp_time_s"] for r in rr);dt=sum(r["dec_time_s"] for r in rr)
        summary.append(dict(
            corpus=corpus,codec=codec,type=rr[0]["type"],profile=rr[0]["profile"],
            raw=raw,size=size,ratio_pct=100.0*size/raw,
            comp_time_s=ct,dec_time_s=dt,
            comp_MBps=(raw/1e6)/ct if ct else None,
            dec_MBps=(raw/1e6)/dt if dt else None,
            sha_all=all(r["sha_ok"] for r in rr),
            canonical_aggregate=(corpus not in ("Artificial","Canterbury-Large"))
        ))

summary.sort(key=lambda x:(x["corpus"],x["ratio_pct"]))
for r in summary:
    print("SUMMARY",json.dumps(r),flush=True)

Path("exp58_multicorpus_results.json").write_text(json.dumps({
    "summary":summary,
    "rows":rows,
    "notes":{
        "Artificial":"Interpret per-file; overall average is not an official canonical benchmark.",
        "Canterbury-Large":"Interpret per-file/subset; overall average is not an official canonical benchmark.",
        "enwik8":"Canonical 100,000,000-byte Large Text Compression Benchmark input."
    }
},indent=2))
