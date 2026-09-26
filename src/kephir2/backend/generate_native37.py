#!/usr/bin/env python3
from pathlib import Path
import argparse
import base64
import gzip
import os
import subprocess
import sys
import tempfile


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True)
    args=ap.parse_args()

    script=Path(__file__).resolve()
    repo=script.parents[3]
    output=Path(args.output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)

    parts=sorted((repo/"engine"/"source_parts").glob("src_gz_*.b64"))
    if not parts:
        raise SystemExit("missing EXP-23 source parts")

    encoded="".join("".join(p.read_text().split()) for p in parts)
    base=gzip.decompress(base64.b64decode(encoded)).decode("utf-8")

    generators=[
        repo/"research"/"generators"/"general"/"make_exp26_source.py",
        repo/"research"/"generators"/"general"/"make_exp27_source.py",
        repo/"research"/"generators"/"general"/"make_exp31_source.py",
        repo/"research"/"generators"/"general"/"make_exp33_source.py",
        repo/"research"/"generators"/"general"/"make_exp37_source.py",
    ]

    with tempfile.TemporaryDirectory(prefix="kephir2_native37_") as td:
        td=Path(td)
        (td/"KEPHIR_2_EXP23_BASE.cpp").write_text(base)

        for gen in generators:
            subprocess.run([sys.executable,str(gen)],cwd=td,check=True)

        src=(td/"KEPHIR_2_EXP37_DUAL_MATCH.cpp").read_text()

    needle="int main(int argc,char**argv){"
    if needle not in src:
        raise SystemExit("EXP-37 main signature not found")
    src=src.replace(
        needle,
        "int kephir37_cli_main(int argc,char**argv){",
        1,
    )

    adapter=r'''
#include "kephir2/native37.hpp"

namespace kephir2::native37 {

std::vector<std::uint8_t> compress_chunk(
    const std::vector<std::uint8_t>& raw) {

    constexpr double LIT=6.55;
    constexpr double MC=9.42;
    constexpr double DPEN=1.20;

    if(raw.empty()) return {};

    const double localDPEN=k2_adaptive_dpen(
        raw,
        DPEN,
        K2_ADAPT_MODE);

    auto ts=parse(raw,LIT,MC,localDPEN);

    std::size_t literals=0;
    for(const auto& t:ts) if(!t.dist) ++literals;

    if(literals > raw.size()*9/10){
        auto out=raw;
        out.push_back(0);
        return out;
    }

    auto out=::encode(raw,ts);
#ifndef NO_INTERNAL_VERIFY
    auto verify=::decode(out,raw.size());
    if(verify!=raw)
        throw std::runtime_error("native37 chunk verification failed");
#endif
    return out;
}

std::vector<std::uint8_t> decompress_chunk(
    const std::vector<std::uint8_t>& compressed,
    std::size_t raw_size) {

    if(raw_size==0){
        if(compressed.empty()) return {};
        if(compressed.size()==1 && compressed.back()==0) return {};
    }

    if(compressed.size()==raw_size+1
       && !compressed.empty()
       && compressed.back()==0){
        return std::vector<std::uint8_t>(
            compressed.begin(),
            compressed.begin()+static_cast<std::ptrdiff_t>(raw_size));
    }

    auto out=::decode(compressed,raw_size);
    if(out.size()!=raw_size)
        throw std::runtime_error("native37 decompression failed");
    return out;
}

} // namespace kephir2::native37
'''

    output.write_text(src+"\n"+adapter)
    print("NATIVE37_SOURCE",output)
    print("NATIVE37_BYTES",output.stat().st_size)


if __name__=="__main__":
    main()
