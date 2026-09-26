#!/usr/bin/env python3
"""
EXP-99 — Python RC1 vs Native K75 Structural Parity Audit

Audits the files that explain most of the remaining ~74 KB ratio gap.

For each selected Silesia file:
- compress with qualified Python KEPHIR RC1;
- compress with current native K75;
- parse the KPF1 file envelope;
- parse inner K75U entries;
- compare entry segmentation, transform modes and compressed sizes.

This is diagnostic only: no thresholds are changed here.
"""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K

FILES=["dickens","mozilla","webster","mr"]


def get_varint(data,pos):
    value=0
    shift=0
    while True:
        if pos>=len(data):
            raise ValueError("truncated varint")
        b=data[pos]; pos+=1
        value |= (b & 0x7f) << shift
        if not (b & 0x80):
            return value,pos
        shift += 7
        if shift>63:
            raise ValueError("varint overflow")


def extract_kpf1_file_blob(path):
    data=path.read_bytes()
    if data[:4] != b"KPF1" or data[4] != 0:
        raise ValueError("not KPF1 file envelope")
    pos=5
    n,pos=get_varint(data,pos)
    name=data[pos:pos+n].decode("utf-8"); pos+=n
    bl,pos=get_varint(data,pos)
    blob=data[pos:pos+bl]; pos+=bl
    if pos!=len(data):
        raise ValueError("KPF1 trailing bytes")
    return name,blob


def parse_k75(blob):
    if blob[:4] != b"K75U":
        raise ValueError("inner blob is not K75U")
    pos=4
    total_raw=struct.unpack_from("<Q",blob,pos)[0]; pos+=8
    count=struct.unpack_from("<I",blob,pos)[0]; pos+=4
    entries=[]
    raw_offset=0
    for index in range(count):
        mode=blob[pos]; pos+=1
        raw_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        comp_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        comp_offset=pos
        pos += comp_size
        entries.append({
            "index":index,
            "raw_offset":raw_offset,
            "raw_size":raw_size,
            "mode":mode,
            "comp_size":comp_size,
            "comp_offset":comp_offset,
        })
        raw_offset += raw_size
    if raw_offset != total_raw:
        raise ValueError("K75 raw total mismatch")
    if pos != len(blob):
        raise ValueError("K75 trailing bytes")
    return {
        "total_raw":total_raw,
        "entry_count":count,
        "entries":entries,
        "blob_bytes":len(blob),
    }


def fresh_model():
    return K.merge_models(K.load_factory(True),{})


def compress_python(src,archive,tmp,model):
    K.compress_file(src,archive,model,tmp)


def compress_native(cli,src,archive):
    subprocess.run(
        [str(cli),"c",str(src),str(archive),"1"],
        check=True,text=True,capture_output=True
    )


def summarize_modes(entries):
    out={}
    for e in entries:
        out[str(e["mode"])]=out.get(str(e["mode"]),0)+1
    return out


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: exp99_k75_parity_audit.py /path/to/native_cli")

    cli=Path(sys.argv[1]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    model=fresh_model()

    work=ROOT/"exp99_audit"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    rows={}
    for name in FILES:
        src=corpus/name
        py_arc=work/f"{name}.python.kpf"
        native_arc=work/f"{name}.native.kpf"
        tmp=work/f"{name}.tmp"
        tmp.mkdir()

        compress_python(src,py_arc,tmp,model)
        compress_native(cli,src,native_arc)

        _,py_blob=extract_kpf1_file_blob(py_arc)
        _,native_blob=extract_kpf1_file_blob(native_arc)
        py=parse_k75(py_blob)
        native=parse_k75(native_blob)

        max_count=max(py["entry_count"],native["entry_count"])
        diffs=[]
        common_raw_layout=(
            [e["raw_size"] for e in py["entries"]]
            ==
            [e["raw_size"] for e in native["entries"]]
        )

        for i in range(max_count):
            pe=py["entries"][i] if i<len(py["entries"]) else None
            ne=native["entries"][i] if i<len(native["entries"]) else None
            if pe is None or ne is None:
                diffs.append({
                    "index":i,
                    "python":pe,
                    "native":ne,
                    "kind":"entry-count",
                })
                continue
            if (
                pe["raw_offset"]!=ne["raw_offset"]
                or pe["raw_size"]!=ne["raw_size"]
                or pe["mode"]!=ne["mode"]
                or pe["comp_size"]!=ne["comp_size"]
            ):
                diffs.append({
                    "index":i,
                    "raw_offset_python":pe["raw_offset"],
                    "raw_offset_native":ne["raw_offset"],
                    "raw_size_python":pe["raw_size"],
                    "raw_size_native":ne["raw_size"],
                    "mode_python":pe["mode"],
                    "mode_native":ne["mode"],
                    "comp_size_python":pe["comp_size"],
                    "comp_size_native":ne["comp_size"],
                    "comp_delta_native_minus_python":
                        ne["comp_size"]-pe["comp_size"],
                })

        row={
            "raw_bytes":src.stat().st_size,
            "python_archive_bytes":py_arc.stat().st_size,
            "native_archive_bytes":native_arc.stat().st_size,
            "archive_delta":native_arc.stat().st_size-py_arc.stat().st_size,
            "python_blob_bytes":py["blob_bytes"],
            "native_blob_bytes":native["blob_bytes"],
            "python_entries":py["entry_count"],
            "native_entries":native["entry_count"],
            "same_raw_layout":common_raw_layout,
            "python_modes":summarize_modes(py["entries"]),
            "native_modes":summarize_modes(native["entries"]),
            "differing_entries":len(diffs),
            "diffs":diffs,
        }
        rows[name]=row

        top=sorted(
            [d for d in diffs if "comp_delta_native_minus_python" in d],
            key=lambda d:abs(d["comp_delta_native_minus_python"]),
            reverse=True
        )[:12]

        print(
            "EXP99_FILE",name,
            "DELTA",row["archive_delta"],
            "PY_ENTRIES",row["python_entries"],
            "NATIVE_ENTRIES",row["native_entries"],
            "SAME_LAYOUT",row["same_raw_layout"],
            "PY_MODES",json.dumps(row["python_modes"],sort_keys=True),
            "NATIVE_MODES",json.dumps(row["native_modes"],sort_keys=True),
            "DIFFS",row["differing_entries"],
            flush=True,
        )
        for d in top:
            print("EXP99_TOPDIFF",name,json.dumps(d,sort_keys=True),flush=True)

    result={
        "experiment":"EXP-99",
        "purpose":"python-native-k75-structural-parity-audit",
        "rows":rows,
    }
    Path("exp99_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )
    print("EXP99_AUDIT_COMPLETE",flush=True)


if __name__=="__main__":
    main()
