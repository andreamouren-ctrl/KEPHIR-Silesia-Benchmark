#!/usr/bin/env python3
from pathlib import Path
import base64
import collections
import math
import subprocess
import sys
import tempfile

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K


def py_metrics(data):
    if not data:
        return 0,0.0,0.0,0.0
    step=max(1,len(data)//8192)
    s=data[::step]
    n=len(s)
    printable=sum(1 for b in s if b in (9,10,13) or 32<=b<127)/n
    zero=s.count(0)/n
    return n,K.entropy(s),printable,zero


def synthetic_fixtures(root):
    root.mkdir(parents=True,exist_ok=True)
    fixtures={}

    fixtures["empty"]=b""
    fixtures["tiny-text"]=b"hello native kephir\n"
    fixtures["tiny-binary"]=bytes(range(64))

    raw=bytes(range(256))*12
    fixtures["encoded-text"]=base64.b64encode(raw)

    code=(
        b"int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n"
        b"struct Node{int x;int y;};\n"
    )
    fixtures["text-code"]=code*32

    config=(
        b"name: value\n"
        b"path: /tmp/data\n"
        b"mode: fast\n"
        b"flag: yes\n"
    )
    fixtures["text-config"]=config*32

    prose=(
        b"This is ordinary prose written with words and spaces. "
        b"The sentence is repeated to make the sample stable and deterministic.\n"
    )
    fixtures["text-prose"]=prose*32

    generic=(b"0123456789!?.,|~ABCxyz" * 64)
    fixtures["text-generic"]=generic

    fixtures["binary-zero"]=(b"\x00"*16+b"\xff"*112)*32
    fixtures["binary-low"]=bytes(range(16))*256
    fixtures["binary-mid"]=bytes(range(64))*128
    fixtures["binary-high"]=bytes(range(256))*32

    paths=[]
    for name,data in fixtures.items():
        p=root/(name+".bin")
        p.write_bytes(data)
        paths.append(p)

    observed={K.classify(p.read_bytes()) for p in paths}
    expected=set(fixtures)
    missing=sorted(expected-observed)
    if missing:
        raise SystemExit(f"synthetic fixture coverage missing classes: {missing}; observed={sorted(observed)}")
    return paths


def tracked_files():
    raw=subprocess.check_output(["git","ls-files","-z"])
    out=[]
    for item in raw.split(b"\0"):
        if not item:
            continue
        p=Path(item.decode())
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


def run_native(exe,paths):
    cmd=[str(exe)]+[str(p) for p in paths]
    proc=subprocess.run(cmd,check=True,text=True,capture_output=True)
    out={}
    for line in proc.stdout.splitlines():
        path,klass,size,samples,entropy,printable,zero=line.split("\t")
        out[path]={
            "class":klass,
            "size":int(size),
            "samples":int(samples),
            "entropy":float(entropy),
            "printable":float(printable),
            "zero":float(zero),
        }
    return out


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: analyzer_parity.py /path/to/kephir2_analyzer_dump")

    exe=Path(sys.argv[1]).resolve()
    if not exe.exists():
        raise SystemExit(f"missing native analyzer utility: {exe}")

    with tempfile.TemporaryDirectory(prefix="kephir2_analyzer_parity_") as td:
        synthetic=synthetic_fixtures(Path(td))
        paths=tracked_files()+synthetic
        native=run_native(exe,paths)

        mismatches=[]
        metric_mismatches=[]
        classes=collections.Counter()

        for p in paths:
            data=p.read_bytes()
            expected=K.classify(data)
            classes[expected]+=1

            row=native.get(str(p))
            if row is None:
                mismatches.append((str(p),expected,"<missing>"))
                continue

            if row["class"]!=expected:
                mismatches.append((str(p),expected,row["class"]))

            samples,h,printable,zero=py_metrics(data)
            if (
                row["size"]!=len(data)
                or row["samples"]!=samples
                or abs(row["entropy"]-h)>1e-12
                or abs(row["printable"]-printable)>1e-12
                or abs(row["zero"]-zero)>1e-12
            ):
                metric_mismatches.append({
                    "path":str(p),
                    "expected":{
                        "size":len(data),"samples":samples,
                        "entropy":h,"printable":printable,"zero":zero,
                    },
                    "native":row,
                })

        print("ANALYZER_PARITY_FILES",len(paths))
        print("ANALYZER_PARITY_CLASSES",dict(sorted(classes.items())))
        print("ANALYZER_CLASS_MISMATCHES",len(mismatches))
        print("ANALYZER_METRIC_MISMATCHES",len(metric_mismatches))

        if mismatches:
            for m in mismatches[:20]:
                print("CLASS_MISMATCH",m)
            raise SystemExit("native/Python classifier parity failed")

        if metric_mismatches:
            for m in metric_mismatches[:5]:
                print("METRIC_MISMATCH",m)
            raise SystemExit("native/Python metric parity failed")

        print("KEPHIR2_ANALYZER_PARITY_PASS")


if __name__=="__main__":
    main()
