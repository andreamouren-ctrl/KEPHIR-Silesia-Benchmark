#!/usr/bin/env python3
"""
KEPHIR 2 — Canonical Router Matrix v1

This module materializes the fixed workload matrix used to evaluate the AUTO
directory-layout router.

The source-repository workload is pinned to an immutable historical commit so
future development commits cannot silently change the benchmark input.

Synthetic workloads are deterministic and intentionally use neutral .dat file
extensions so extension/name cannot influence content-first routing.
"""
from pathlib import Path
import os
import random
import shutil
import subprocess

PINNED_REPOSITORY_SHA="31f7e6099cec307ad934fd9ec8e6760441567ab5"
MATRIX_VERSION="router-matrix-v1"


def write_repeat(path,pattern,size):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not pattern:
        pattern=b"\x00"
    q,r=divmod(size,len(pattern))
    path.write_bytes(pattern*q+pattern[:r])


def materialize_pinned_repository(root):
    dst=root/"repository"
    dst.mkdir(parents=True,exist_ok=True)

    # The CI workflow using this matrix must checkout with fetch-depth: 0, or
    # explicitly fetch PINNED_REPOSITORY_SHA before calling this function.
    check=subprocess.run(
        ["git","cat-file","-e",f"{PINNED_REPOSITORY_SHA}^{{commit}}"],
        capture_output=True,
    )
    if check.returncode!=0:
        subprocess.run(
            ["git","fetch","--depth=1","origin",PINNED_REPOSITORY_SHA],
            check=True,
        )

    raw=subprocess.check_output(
        ["git","ls-tree","-r","-z","--name-only",PINNED_REPOSITORY_SHA]
    )
    for item in raw.split(b"\0"):
        if not item:
            continue
        rel=Path(item.decode("utf-8"))
        data=subprocess.check_output(
            ["git","show",f"{PINNED_REPOSITORY_SHA}:{rel.as_posix()}"]
        )
        target=dst/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    return dst


def make_many_tiny_source(root):
    dst=root/"many_tiny_source"
    dst.mkdir()
    base=(
        b"int compute(int x){ return (x*17)+3; }\n"
        b"struct Item { int a; int b; int c; };\n"
        b"if(value<limit){value+=step;}else{value-=step;}\n"
    )
    for i in range(1024):
        payload=(base+f"// unit {i:04d}\n".encode())*32
        (dst/f"f{i:04d}.dat").write_bytes(payload)
    return dst


def make_homogeneous_large(root):
    dst=root/"homogeneous_large"
    dst.mkdir()
    pattern=(
        b"The same project record is repeated across several large files. "
        b"Cross-file redundancy should remain highly visible to a solid stream.\n"
    )
    for i in range(4):
        write_repeat(dst/f"f{i}.dat",pattern,3*1024*1024)
    return dst


def make_mixed_content(root):
    dst=root/"mixed_content"
    dst.mkdir()
    one=1024*1024
    write_repeat(dst/"a.dat",b"int f(int x){return x*x+17;}\n",one)
    write_repeat(dst/"b.dat",b"ordinary prose words and spaces form a natural language paragraph.\n",one)
    write_repeat(dst/"c.dat",b"name: value\npath: /var/data\nmode: fast\n",one)
    write_repeat(dst/"d.dat",(b"\x00"*16+b"\xff"*112),one)
    write_repeat(dst/"e.dat",bytes(range(16)),one)
    write_repeat(dst/"f.dat",bytes(range(64)),one)
    rng=random.Random(8001)
    (dst/"g.dat").write_bytes(rng.randbytes(one))
    write_repeat(dst/"h.dat",b"0123456789!?.,|~ABCxyz",one)
    return dst


def make_incompressible(root):
    dst=root/"incompressible"
    dst.mkdir()
    rng=random.Random(8002)
    for i in range(4):
        (dst/f"f{i}.dat").write_bytes(rng.randbytes(2*1024*1024))
    return dst


def make_zero_rich(root):
    dst=root/"zero_rich"
    dst.mkdir()
    pattern=(
        b"\x00\x00\x00\x00"
        b"\x01\x00\x00\x00"
        b"\x02\x00\x00\x00"
        b"\x03\x00\x00\x00"
    )
    for i in range(8):
        write_repeat(dst/f"f{i}.dat",pattern,1024*1024)
    return dst


def make_redundant_backup(root):
    dst=root/"redundant_backup"
    dst.mkdir()
    block=(
        b"backup-record|customer=000001|state=active|timestamp=2026-09-26\n"
        b"backup-record|customer=000002|state=active|timestamp=2026-09-26\n"
    )
    common=(block*((512*1024)//len(block)+1))[:512*1024]
    for i in range(16):
        tail=(f"snapshot={i:02d}\n".encode()*1024)
        data=bytearray(common)
        data[-len(tail):]=tail
        (dst/f"f{i}.dat").write_bytes(data)
    return dst


def materialize_matrix(root,silesia):
    root=Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    silesia=Path(silesia)
    if not silesia.exists():
        raise FileNotFoundError("canonical Silesia directory missing")

    return {
        "repository":materialize_pinned_repository(root),
        "silesia":silesia,
        "many_tiny_source":make_many_tiny_source(root),
        "homogeneous_large":make_homogeneous_large(root),
        "mixed_content":make_mixed_content(root),
        "incompressible":make_incompressible(root),
        "zero_rich":make_zero_rich(root),
        "redundant_backup":make_redundant_backup(root),
    }
