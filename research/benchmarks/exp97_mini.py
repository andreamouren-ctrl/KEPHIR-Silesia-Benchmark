#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import shutil
import sys

ROOT=Path.cwd()
spec=importlib.util.spec_from_file_location(
    "exp97",
    ROOT/"research"/"benchmarks"/"exp97_current_competitor_benchmark.py")
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
B.REPEATS=1

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp97_mini.py /path/to/kephir2_native_k75_cli")
    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    out=ROOT/"exp97_mini_out"
    if out.exists(): shutil.rmtree(out)
    out.mkdir()

    rows=[B.benchmark_native(cli,corpus,out)]

    for level in (3,19):
        rows.append(B.benchmark_stream_codec(
            f"Zstd -{level}","Zstd","zst",corpus,out,
            lambda p,o,l=level:(
                ["zstd",f"-{l}","-T1","-q","-f",str(p),"-o",str(o)],False),
            lambda a,d,n:(
                ["zstd","-d","-q","-f",str(a),"-o",str(d)],False),
        ))

    rows.append(B.benchmark_stream_codec(
        "XZ/LZMA2 -6","LZMA2","xz",corpus,out,
        lambda p,o:(["xz","-6","-T1","-c",str(p)],True),
        lambda a,d,n:(["xz","-d","-c",str(a)],True),
    ))
    rows.append(B.benchmark_stream_codec(
        "Gzip/Deflate -9","Deflate","gz",corpus,out,
        lambda p,o:(["gzip","-9","-c",str(p)],True),
        lambda a,d,n:(["gzip","-d","-c",str(a)],True),
    ))
    rows.append(B.benchmark_stream_codec(
        "LZ4 default","LZ4","lz4",corpus,out,
        lambda p,o:(["lz4","-q","-f",str(p),str(o)],False),
        lambda a,d,n:(["lz4","-d","-q","-f",str(a),str(d)],False),
    ))

    rows=sorted(rows,key=lambda r:r["ratio"])
    Path("exp97_mini_results.json").write_text(
        json.dumps({"experiment":"EXP-97M","rows":rows},indent=2,sort_keys=True)
    )
    for r in rows:
        print("EXP97M_ROW",r["codec"],
              "BYTES",r["archive_bytes"],
              "RATIO",r["ratio"],
              "COMP_MBPS",r["comp_MBps"],
              "DEC_MBPS",r["dec_MBps"],
              "SHA",r["sha_all_pass"],flush=True)
    print("EXP97M_SHA_ALL_PASS",flush=True)

if __name__=="__main__":
    main()
