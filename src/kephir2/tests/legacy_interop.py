#!/usr/bin/env python3
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile


def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def write_repeat(path,pattern,size):
    path.parent.mkdir(parents=True,exist_ok=True)
    q,r=divmod(size,len(pattern))
    path.write_bytes(pattern*q+pattern[:r])


def make_file(path):
    data=bytearray()
    text=(b"int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n")
    while len(data)<180*1024:
        data.extend(text)
    x=0x12345678
    while len(data)<360*1024:
        x ^= (x << 13) & 0xffffffff
        x ^= (x >> 17)
        x ^= (x << 5) & 0xffffffff
        data.append(x & 0xff)
    path.write_bytes(bytes(data[:360*1024]))


def make_directory(root):
    write_repeat(
        root/"code.dat",
        b"int f(int x){return x*x+17;}\n",
        96*1024,
    )
    write_repeat(
        root/"docs"/"prose.dat",
        b"ordinary prose words and spaces form a natural sentence. ",
        96*1024,
    )
    (root/"tiny.dat").write_bytes(b"hello")
    b=root/"binary"/"zero.dat"
    b.parent.mkdir(parents=True,exist_ok=True)
    b.write_bytes((b"\x00\x00\x01\x00\x02\x00")*(32*1024))


def compare_trees(a,b):
    af=sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    bf=sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    assert af==bf,(af,bf)
    for rel in af:
        assert sha256(a/rel)==sha256(b/rel),rel


def run(cmd,cwd=None):
    print("RUN"," ".join(str(x) for x in cmd),flush=True)
    subprocess.run(cmd,cwd=cwd,check=True)


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: legacy_interop.py /path/to/kephir2_interop_tool")

    repo=Path.cwd()
    native=Path(sys.argv[1]).resolve()
    historical=repo/"kephir37"

    if not native.exists():
        raise SystemExit(f"missing native tool: {native}")
    if not historical.exists():
        raise SystemExit(f"missing historical kephir37: {historical}")

    with tempfile.TemporaryDirectory(prefix="kephir2_legacy_interop_") as td:
        td=Path(td)

        # Single-file: native -> historical.
        raw=td/"sample.bin"
        make_file(raw)
        native_arc=td/"native_file.kpf"
        py_out=td/"py_file_out"

        run([str(native),"compress",str(raw),str(native_arc)])
        run([
            sys.executable,
            str(repo/"release"/"kephir_final.py"),
            "extract",
            str(native_arc),
            str(py_out),
        ],cwd=repo)
        assert sha256(raw)==sha256(py_out/raw.name)
        print("INTEROP_NATIVE_TO_LEGACY_FILE_PASS",flush=True)

        # Single-file: historical -> native.
        historical_arc=td/"legacy_file.kpf"
        native_out=td/"native_file_out"
        run([
            sys.executable,
            str(repo/"release"/"kephir_final.py"),
            "compress",
            str(raw),
            str(historical_arc),
            "--cold",
            "--workers","1",
            "--no-verify",
        ],cwd=repo)
        run([str(native),"extract",str(historical_arc),str(native_out)])
        assert sha256(raw)==sha256(native_out/raw.name)
        print("INTEROP_LEGACY_TO_NATIVE_FILE_PASS",flush=True)

        # Directory: native -> historical.
        directory=td/"dir_input"
        make_directory(directory)
        native_dir_arc=td/"native_dir.kpf"
        py_dir_out=td/"py_dir_out"

        run([str(native),"compress",str(directory),str(native_dir_arc)])
        run([
            sys.executable,
            str(repo/"release"/"kephir_final.py"),
            "extract",
            str(native_dir_arc),
            str(py_dir_out),
        ],cwd=repo)
        compare_trees(directory,py_dir_out)
        print("INTEROP_NATIVE_TO_LEGACY_DIRECTORY_PASS",flush=True)

        # Directory: historical -> native.
        legacy_dir_arc=td/"legacy_dir.kpf"
        native_dir_out=td/"native_dir_out"
        run([
            sys.executable,
            str(repo/"release"/"kephir_final.py"),
            "compress",
            str(directory),
            str(legacy_dir_arc),
            "--cold",
            "--workers","1",
            "--no-verify",
        ],cwd=repo)
        run([str(native),"extract",str(legacy_dir_arc),str(native_dir_out)])
        compare_trees(directory,native_dir_out)
        print("INTEROP_LEGACY_TO_NATIVE_DIRECTORY_PASS",flush=True)

    print("KEPHIR2_LEGACY_INTEROP_ALL_PASS",flush=True)


if __name__=="__main__":
    main()
