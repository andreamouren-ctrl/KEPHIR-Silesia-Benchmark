#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K


def write_repeat(path, pattern, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    q, r = divmod(size, len(pattern))
    path.write_bytes(pattern*q + pattern[:r])


def make_fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    write_repeat(root/"code.dat", b"int f(int x){return x*x+17;}\n", 4096)
    write_repeat(
        root/"docs"/"prose.dat",
        b"ordinary prose words and spaces form a natural sentence.\n",
        4096,
    )
    write_repeat(root/"binary"/"zero.dat", b"\x00\x00\x01\x00\x02\x00", 4096)
    write_repeat(root/"binary"/"low.dat", bytes(range(16)), 4096)
    write_repeat(root/"utf8"/"micro_µ.dat", b"name: value\nmode: fast\n", 4096)
    (root/"tiny.dat").write_bytes(b"hello")
    return root


def make_tracked_snapshot(root):
    root.mkdir(parents=True, exist_ok=True)
    raw=subprocess.check_output(["git","ls-files","-z"])
    for item in raw.split(b"\0"):
        if not item:
            continue
        src=Path(item.decode("utf-8"))
        if not src.is_file() or src.is_symlink():
            continue
        dst=root/src
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src,dst)
    return root


def python_plan(root):
    records=[]
    group_bytes={}
    group_counts={}
    group_offsets={}

    for p in K.collect_directory(root):
        raw=p.read_bytes()
        group=K.classify(raw)
        path=p.relative_to(root).as_posix()
        offset=group_bytes.get(group,0)
        records.append({
            "path":path,
            "group":group,
            "size":len(raw),
            "offset":offset,
        })
        group_bytes[group]=offset+len(raw)
        group_counts[group]=group_counts.get(group,0)+1

    names=sorted(group_bytes)
    gids={g:i for i,g in enumerate(names)}
    manifest_records=[
        {"path":r["path"],"group":r["group"],"size":r["size"]}
        for r in records
    ]
    manifest=K.build_manifest(manifest_records,gids)

    return {
        "manifest_hex":manifest.hex(),
        "groups":[(i,g,group_bytes[g]) for i,g in enumerate(names)],
        "files":[
            (
                r["path"],r["group"],r["group"],gids[r["group"]],
                r["size"],r["offset"]
            )
            for r in records
        ],
    }


def native_plan(exe, root):
    proc=subprocess.run(
        [str(exe),str(root)],
        check=True,text=True,capture_output=True
    )
    manifest_hex=None
    groups=[]
    files=[]
    for line in proc.stdout.splitlines():
        parts=line.split("\t")
        if not parts:
            continue
        if parts[0]=="MANIFEST_HEX":
            manifest_hex=parts[1]
        elif parts[0]=="GROUP":
            groups.append((int(parts[1]),parts[2],int(parts[3])))
        elif parts[0]=="FILE":
            files.append((
                parts[1],parts[2],parts[3],int(parts[4]),
                int(parts[5]),int(parts[6])
            ))
        else:
            raise RuntimeError(f"unexpected native packing line: {line!r}")
    return {
        "manifest_hex":manifest_hex,
        "groups":groups,
        "files":files,
    }


def check(label, root, exe):
    expected=python_plan(root)
    native=native_plan(exe,root)

    assert native["manifest_hex"]==expected["manifest_hex"], label+" manifest mismatch"
    assert native["groups"]==expected["groups"], label+" group table mismatch"
    assert native["files"]==expected["files"], label+" file plan mismatch"

    print(
        "PACKING_PARITY",
        label,
        "FILES",len(expected["files"]),
        "GROUPS",len(expected["groups"]),
        "MANIFEST_BYTES",len(bytes.fromhex(expected["manifest_hex"])),
    )


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: packing_parity.py /path/to/kephir2_packing_dump")

    exe=Path(sys.argv[1]).resolve()
    if not exe.exists():
        raise SystemExit(f"missing packing utility: {exe}")

    with tempfile.TemporaryDirectory(prefix="kephir2_packing_parity_") as td:
        td=Path(td)
        fixture=make_fixture(td/"fixture")
        snapshot=make_tracked_snapshot(td/"tracked")

        check("fixture",fixture,exe)
        check("tracked",snapshot,exe)

    print("PACKING_MANIFEST_PARITY_PASS")
    print("PACKING_RECORD_PARITY_PASS")
    print("PACKING_GROUP_PARITY_PASS")


if __name__=="__main__":
    main()
