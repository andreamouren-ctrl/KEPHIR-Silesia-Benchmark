#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K
E=K.E

FILES=["dickens","webster"]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def get_varint(data,pos):
    value=0; shift=0
    while True:
        b=data[pos]; pos+=1
        value |= (b & 0x7f) << shift
        if not (b & 0x80): return value,pos
        shift += 7

def kpf_blob(path):
    data=path.read_bytes()
    assert data[:4]==b"KPF1" and data[4]==0
    pos=5
    n,pos=get_varint(data,pos); pos+=n
    bl,pos=get_varint(data,pos)
    blob=data[pos:pos+bl]; pos+=bl
    assert pos==len(data)
    return blob

def parse_k75(blob):
    assert blob[:4]==b"K75U"
    pos=4
    total=struct.unpack_from("<Q",blob,pos)[0]; pos+=8
    count=struct.unpack_from("<I",blob,pos)[0]; pos+=4
    out=[]; raw_off=0
    for i in range(count):
        mode=blob[pos]; pos+=1
        raw_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        cs=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        comp=blob[pos:pos+cs]; pos+=cs
        out.append((i,raw_off,raw_size,mode,comp))
        raw_off += raw_size
    assert raw_off==total and pos==len(blob)
    return out

def fresh_model():
    return K.merge_models(K.load_factory(True),{})

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp101_transform_parity.py NATIVE_CLI")
    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp101_transform_parity"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()

    model=fresh_model()
    rows={}
    all_equal=True

    for name in FILES:
        src=corpus/name
        raw=src.read_bytes()
        py_arc=work/f"{name}.py.kpf"
        na_arc=work/f"{name}.native.kpf"
        tmp=work/f"{name}.tmp"; tmp.mkdir()

        K.compress_file(src,py_arc,model,tmp/"pyenc")
        subprocess.run(
            [str(cli),"c",str(src),str(na_arc),"1"],
            check=True,text=True,capture_output=True
        )

        pe=parse_k75(kpf_blob(py_arc))
        ne=parse_k75(kpf_blob(na_arc))
        assert len(pe)==len(ne)

        file_rows=[]
        for p,n in zip(pe,ne):
            pi,po,psz,pm,pcomp=p
            ni,no,nsz,nm,ncomp=n
            same_layout=(po,psz,pm)==(no,nsz,nm)

            expected=E.transform(raw[po:po+psz],pm)
            py_trans=E.dp(pcomp,tmp/f"p_{pi}")
            na_trans=E.dp(ncomp,tmp/f"n_{ni}")

            row={
                "index":pi,
                "same_layout":same_layout,
                "mode":pm,
                "raw_offset":po,
                "raw_size":psz,
                "expected_bytes":len(expected),
                "python_transformed_bytes":len(py_trans),
                "native_transformed_bytes":len(na_trans),
                "expected_sha":sha(expected),
                "python_sha":sha(py_trans),
                "native_sha":sha(na_trans),
                "python_matches_expected":py_trans==expected,
                "native_matches_expected":na_trans==expected,
                "python_equals_native":py_trans==na_trans,
                "python_comp_bytes":len(pcomp),
                "native_comp_bytes":len(ncomp),
            }
            file_rows.append(row)
            all_equal &= (
                same_layout
                and py_trans==expected
                and na_trans==expected
                and py_trans==na_trans
            )

        rows[name]=file_rows
        bad=[r for r in file_rows if not (
            r["same_layout"]
            and r["python_matches_expected"]
            and r["native_matches_expected"]
            and r["python_equals_native"]
        )]
        print(
            "EXP101_FILE",name,
            "ENTRIES",len(file_rows),
            "TRANSFORM_MISMATCHES",len(bad),
            "ALL_TRANSFORMS_EQUAL",not bad,
            flush=True
        )

    result={
        "experiment":"EXP-101",
        "all_transforms_equal":all_equal,
        "rows":rows,
    }
    Path("exp101_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )
    print("EXP101_ALL_TRANSFORMS_EQUAL",all_equal,flush=True)

if __name__=="__main__":
    main()
