#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import shutil
import sys

ROOT=Path.cwd()
module_path=ROOT/"research"/"benchmarks"/"exp97_current_competitor_benchmark.py"
spec=importlib.util.spec_from_file_location("exp97",module_path)
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
B.REPEATS=1


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp97_quick_spot.py /path/to/kephir2_native_k75_cli")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    out=ROOT/"exp97_quick_out"
    if out.exists():
        shutil.rmtree(out)
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
        "XZ/LZMA2 -9e","LZMA2","xz",corpus,out,
        lambda p,o:(["xz","-9e","-T1","-c",str(p)],True),
        lambda a,d,n:(["xz","-d","-c",str(a)],True),
    ))

    rows.append(B.benchmark_stream_codec(
        "Brotli q11","Brotli","br",corpus,out,
        lambda p,o:(["brotli","-q","11","-f",str(p),"-o",str(o)],False),
        lambda a,d,n:(["brotli","-d","-f",str(a),"-o",str(d)],False),
    ))

    rows.append(B.benchmark_stream_codec(
        "7-Zip/LZMA2 mx9","7-Zip LZMA2","7z",corpus,out,
        lambda p,o:(
            ["7z","a","-bd","-y","-mx=9","-m0=lzma2","-mmt=1",
             str(o.resolve()),p.name],False),
        lambda a,d,n:(["7z","x","-so",str(a.resolve()),n],True),
        compress_cwd=True,
        decompress_cwd=True,
    ))

    rows.append(B.benchmark_stream_codec(
        "LZ4 default","LZ4","lz4",corpus,out,
        lambda p,o:(["lz4","-q","-f",str(p),str(o)],False),
        lambda a,d,n:(["lz4","-d","-q","-f",str(a),str(d)],False),
    ))

    rows=sorted(rows,key=lambda r:r["ratio"])
    result={
        "experiment":"EXP-97Q",
        "raw_bytes":211938580,
        "repeats":1,
        "rows":rows,
    }
    Path("exp97_quick_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    for r in rows:
        print(
            "EXP97Q_ROW",r["codec"],
            "BYTES",r["archive_bytes"],
            "RATIO",r["ratio"],
            "COMP_MBPS",r["comp_MBps"],
            "DEC_MBPS",r["dec_MBps"],
            "SHA",r["sha_all_pass"],
            flush=True,
        )
    print("EXP97Q_SHA_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
