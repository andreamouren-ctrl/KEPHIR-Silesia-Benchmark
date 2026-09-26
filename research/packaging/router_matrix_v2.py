#!/usr/bin/env python3
"""
KEPHIR 2 — Router Matrix v2 Holdout

Extends the frozen Router Matrix v1 with unseen deterministic workload shapes
for validating the EXP-86 cross-file groupability estimator.

All synthetic files use neutral .dat names. No extension/name signal is useful
to the router.
"""
from pathlib import Path
import random

import router_matrix_v1 as V1

MATRIX_VERSION="router-matrix-v2-holdout"

HOLDOUT_NAMES=(
    "two_large_repeated_classes",
    "one_file_per_class_large",
    "balanced_medium_repeated",
    "dominant_large_with_minorities",
    "many_medium_four_groups",
    "two_groups_imbalanced_large",
    "two_groups_balanced_large",
    "three_groups_balanced_large",
)


def write_repeat(path,pattern,size):
    V1.write_repeat(path,pattern,size)


CODE=b"int transform(int x){return (x*31)+7;}\nstruct Row{int a;int b;int c;};\n"
PROSE=b"ordinary language words and spaces form a stable paragraph for compression.\n"
CONFIG=b"name: value\nmode: fast\npath: /data/item\nflag: yes\n"
ZERO=(b"\x00"*16+b"\xff"*112)


def make_two_large_repeated_classes(root):
    dst=root/"two_large_repeated_classes"; dst.mkdir()
    for i in range(3):
        write_repeat(dst/f"a{i}.dat",CODE,1024*1024)
    for i in range(3):
        write_repeat(dst/f"b{i}.dat",ZERO,1024*1024)
    return dst


def make_one_file_per_class_large(root):
    dst=root/"one_file_per_class_large"; dst.mkdir()
    one=1024*1024
    write_repeat(dst/"a.dat",CODE,one)
    write_repeat(dst/"b.dat",PROSE,one)
    write_repeat(dst/"c.dat",CONFIG,one)
    write_repeat(dst/"d.dat",ZERO,one)
    write_repeat(dst/"e.dat",bytes(range(16)),one)
    rng=random.Random(8701)
    (dst/"f.dat").write_bytes(rng.randbytes(one))
    return dst


def make_balanced_medium_repeated(root):
    dst=root/"balanced_medium_repeated"; dst.mkdir()
    one=256*1024
    for i in range(6):
        write_repeat(dst/f"a{i}.dat",CODE,one)
    for i in range(6):
        write_repeat(dst/f"b{i}.dat",ZERO,one)
    return dst


def make_dominant_large_with_minorities(root):
    dst=root/"dominant_large_with_minorities"; dst.mkdir()
    one=1024*1024
    for i in range(6):
        write_repeat(dst/f"a{i}.dat",CODE,one)
    write_repeat(dst/"b0.dat",ZERO,one)
    rng=random.Random(8702)
    (dst/"c0.dat").write_bytes(rng.randbytes(one))
    return dst


def make_many_medium_four_groups(root):
    dst=root/"many_medium_four_groups"; dst.mkdir()
    one=64*1024
    patterns=(CODE,PROSE,CONFIG,ZERO)
    for g,pattern in enumerate(patterns):
        for i in range(10):
            write_repeat(dst/f"g{g}_{i:02d}.dat",pattern,one)
    return dst


def make_two_groups_imbalanced_large(root):
    dst=root/"two_groups_imbalanced_large"; dst.mkdir()
    one=1024*1024
    for i in range(4):
        write_repeat(dst/f"a{i}.dat",CODE,one)
    write_repeat(dst/"b0.dat",ZERO,one)
    return dst


def make_two_groups_balanced_large(root):
    dst=root/"two_groups_balanced_large"; dst.mkdir()
    one=1024*1024
    for i in range(3):
        write_repeat(dst/f"a{i}.dat",CODE,one)
    for i in range(3):
        write_repeat(dst/f"b{i}.dat",ZERO,one)
    return dst


def make_three_groups_balanced_large(root):
    dst=root/"three_groups_balanced_large"; dst.mkdir()
    one=1024*1024
    for i in range(2):
        write_repeat(dst/f"a{i}.dat",CODE,one)
    for i in range(2):
        write_repeat(dst/f"b{i}.dat",CONFIG,one)
    for i in range(2):
        write_repeat(dst/f"c{i}.dat",ZERO,one)
    return dst


def materialize_matrix(root,silesia):
    root=Path(root)
    datasets=V1.materialize_matrix(root,silesia)
    datasets.update({
        "two_large_repeated_classes":make_two_large_repeated_classes(root),
        "one_file_per_class_large":make_one_file_per_class_large(root),
        "balanced_medium_repeated":make_balanced_medium_repeated(root),
        "dominant_large_with_minorities":make_dominant_large_with_minorities(root),
        "many_medium_four_groups":make_many_medium_four_groups(root),
        "two_groups_imbalanced_large":make_two_groups_imbalanced_large(root),
        "two_groups_balanced_large":make_two_groups_balanced_large(root),
        "three_groups_balanced_large":make_three_groups_balanced_large(root),
    })
    return datasets
