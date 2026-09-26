#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K


VALUES=[
    0,
    1,
    127,
    128,
    255,
    300,
    16384,
    0x1_0000_0000,
    0x7fff_ffff_ffff_ffff,
]

RECORDS=[
    {"path":"docs/readme.txt","group":"g0","size":12},
    {"path":"docs/source/main.cpp","group":"g1","size":345},
    {"path":"docs/source/µ.dat","group":"g2","size":70000},
    {"path":"z.bin","group":"g1","size":0x1_0000_0000},
]
NAMES=["g0","g1","g2"]
GIDS={name:i for i,name in enumerate(NAMES)}


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: archive_parity.py /path/to/kephir2_archive_dump")

    exe=Path(sys.argv[1]).resolve()
    proc=subprocess.run([str(exe)],check=True,text=True,capture_output=True)

    native={}
    for line in proc.stdout.splitlines():
        key,value=line.split("\t",1)
        native[key]=value.strip()

    py_varints=bytearray()
    for value in VALUES:
        K.put_varint(py_varints,value)

    py_manifest=K.build_manifest(RECORDS,GIDS)

    assert native["VARINT_HEX"] == bytes(py_varints).hex(), (
        native["VARINT_HEX"], bytes(py_varints).hex()
    )
    assert native["MANIFEST_HEX"] == py_manifest.hex(), (
        native["MANIFEST_HEX"], py_manifest.hex()
    )

    # Cross-language decode: Python must parse the exact bytes emitted by C++.
    decoded=K.parse_manifest(bytes.fromhex(native["MANIFEST_HEX"]),NAMES)
    assert decoded == RECORDS, (decoded,RECORDS)

    # Verify Python varint decoder sees the same concatenated native stream.
    raw=bytes.fromhex(native["VARINT_HEX"])
    pos=0
    got=[]
    for _ in VALUES:
        value,pos=K.get_varint(raw,pos)
        got.append(value)
    assert got == VALUES
    assert pos == len(raw)

    print("ARCHIVE_VARINT_PARITY_PASS")
    print("ARCHIVE_MANIFEST_PARITY_PASS")
    print("ARCHIVE_CROSS_DECODE_PASS")


if __name__=="__main__":
    main()
