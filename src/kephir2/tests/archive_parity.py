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

FILE_NAME="sample.txt"
FILE_BLOB=bytes([0x00,0x01,0xff])+b"K75"
GROUPS=[
    (12,bytes([0x10,0x11])),
    (0x1_0000_0200,bytes([0x20,0x21,0x22])),
    (70000,bytes([0x30])),
]


def build_file_envelope():
    out=bytearray(K.MAGIC)
    out.append(K.TYPE_FILE)
    name=FILE_NAME.encode("utf-8")
    K.put_varint(out,len(name)); out.extend(name)
    K.put_varint(out,len(FILE_BLOB)); out.extend(FILE_BLOB)
    return bytes(out)


def build_directory_envelope(manifest):
    out=bytearray(K.MAGIC)
    out.append(K.TYPE_DIRECTORY)
    K.put_varint(out,len(NAMES))
    for name in NAMES:
        b=name.encode("utf-8")
        K.put_varint(out,len(b)); out.extend(b)
    K.put_varint(out,len(manifest)); out.extend(manifest)
    for rawlen,blob in GROUPS:
        K.put_varint(out,rawlen)
        K.put_varint(out,len(blob)); out.extend(blob)
    return bytes(out)


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
    py_file=build_file_envelope()
    py_dir=build_directory_envelope(py_manifest)

    assert native["VARINT_HEX"] == bytes(py_varints).hex(), (
        native["VARINT_HEX"], bytes(py_varints).hex()
    )
    assert native["MANIFEST_HEX"] == py_manifest.hex(), (
        native["MANIFEST_HEX"], py_manifest.hex()
    )
    assert native["FILE_KPF1_HEX"] == py_file.hex(), (
        native["FILE_KPF1_HEX"], py_file.hex()
    )
    assert native["DIR_KPF1_HEX"] == py_dir.hex(), (
        native["DIR_KPF1_HEX"], py_dir.hex()
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

    # Parse the C++ KPF1 directory envelope using the Python primitives.
    raw_dir=bytes.fromhex(native["DIR_KPF1_HEX"])
    assert raw_dir[:4] == K.MAGIC
    assert raw_dir[4] == K.TYPE_DIRECTORY
    pos=5
    ng,pos=K.get_varint(raw_dir,pos)
    names=[]
    for _ in range(ng):
        n,pos=K.get_varint(raw_dir,pos)
        names.append(raw_dir[pos:pos+n].decode("utf-8"))
        pos+=n
    ml,pos=K.get_varint(raw_dir,pos)
    manifest=raw_dir[pos:pos+ml]; pos+=ml
    assert names == NAMES
    assert K.parse_manifest(manifest,names) == RECORDS
    parsed_groups=[]
    for _ in range(ng):
        rawlen,pos=K.get_varint(raw_dir,pos)
        bl,pos=K.get_varint(raw_dir,pos)
        blob=raw_dir[pos:pos+bl]; pos+=bl
        parsed_groups.append((rawlen,blob))
    assert parsed_groups == GROUPS
    assert pos == len(raw_dir)

    print("ARCHIVE_VARINT_PARITY_PASS")
    print("ARCHIVE_MANIFEST_PARITY_PASS")
    print("ARCHIVE_KPF1_FILE_PARITY_PASS")
    print("ARCHIVE_KPF1_DIRECTORY_PARITY_PASS")
    print("ARCHIVE_CROSS_DECODE_PASS")


if __name__=="__main__":
    main()
