#!/usr/bin/env python3
"""
EXP-108 — Adaptive Word Dictionary Transform prototype

Offline R&D only. Does not change KPF1/K75U.

For each current native K75 entry that is text-like:
- build reversible per-chunk adaptive word dictionaries;
- test 32/64/127 dictionary entries;
- encode transformed bytes through the exact native37 blob encoder;
- compare production AUR2 byte size with the current stored entry;
- verify transform roundtrip.

Reports the exact archive-size potential of a future K75 mode 7.
"""
from pathlib import Path
import collections
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/"release"))
import kephir_final as K
E=K.E

FILES=[
    "dickens","mozilla","mr","nci","ooffice","osdb",
    "reymont","samba","sao","webster","x-ray","xml",
]

TOKEN_BASE=0x80
TOKEN_MAX=0xFE
ESC=0xFF
MAX_TOKENS=TOKEN_MAX-TOKEN_BASE+1


def get_varint(data,pos):
    value=0; shift=0
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


def extract_kpf_blob(path):
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
    entries=[]
    raw_offset=0
    for index in range(count):
        mode=blob[pos]; pos+=1
        raw_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        comp_size=struct.unpack_from("<I",blob,pos)[0]; pos+=4
        pos += comp_size
        entries.append({
            "index":index,
            "raw_offset":raw_offset,
            "raw_size":raw_size,
            "mode":mode,
            "comp_size":comp_size,
            "stored_bytes":9+comp_size,
        })
        raw_offset += raw_size
    assert raw_offset==total and pos==len(blob)
    return entries


def is_letter(b):
    return (65<=b<=90) or (97<=b<=122)


def collect_words(raw):
    counts=collections.Counter()
    i=0
    while i<len(raw):
        if not is_letter(raw[i]):
            i+=1
            continue
        j=i+1
        while j<len(raw) and is_letter(raw[j]):
            j+=1
        word=raw[i:j]
        if 3<=len(word)<=31:
            counts[word]+=1
        i=j
    return counts


def choose_dictionary(raw,limit):
    counts=collect_words(raw)
    scored=[]
    for word,freq in counts.items():
        if freq<2:
            continue
        # One-byte token replaces len(word) bytes. Header stores one-byte
        # length plus the word itself. The fixed WDT header is handled later.
        estimated=(len(word)-1)*freq-(1+len(word))
        if estimated>0:
            scored.append((estimated,freq,len(word),word))
    scored.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3]))
    return [x[3] for x in scored[:min(limit,MAX_TOKENS)]]


def wdt_encode(raw,limit):
    dictionary=choose_dictionary(raw,limit)
    index={w:i for i,w in enumerate(dictionary)}

    out=bytearray(b"WDT1")
    out.append(len(dictionary))
    for word in dictionary:
        out.append(len(word))
        out.extend(word)

    i=0
    while i<len(raw):
        b=raw[i]
        if is_letter(b):
            j=i+1
            while j<len(raw) and is_letter(raw[j]):
                j+=1
            word=raw[i:j]
            token=index.get(word)
            if token is not None:
                out.append(TOKEN_BASE+token)
            else:
                out.extend(word)
            i=j
            continue

        if b>=TOKEN_BASE:
            out.append(ESC)
            out.append(b)
        else:
            out.append(b)
        i+=1

    return bytes(out),dictionary


def wdt_decode(data):
    if len(data)<5 or data[:4]!=b"WDT1":
        raise ValueError("bad WDT1 stream")
    pos=4
    count=data[pos]; pos+=1
    dictionary=[]
    for _ in range(count):
        if pos>=len(data):
            raise ValueError("truncated WDT dictionary")
        n=data[pos]; pos+=1
        if pos+n>len(data):
            raise ValueError("truncated WDT word")
        dictionary.append(data[pos:pos+n])
        pos+=n

    out=bytearray()
    while pos<len(data):
        b=data[pos]; pos+=1
        if b==ESC:
            if pos>=len(data):
                raise ValueError("truncated WDT escape")
            out.append(data[pos]); pos+=1
        elif TOKEN_BASE<=b<=TOKEN_MAX:
            idx=b-TOKEN_BASE
            if idx>=len(dictionary):
                raise ValueError("invalid WDT token")
            out.extend(dictionary[idx])
        else:
            out.append(b)
    return bytes(out)


def native37_size(cli,payload,tmpbase):
    inp=tmpbase.with_suffix(".bin")
    out=tmpbase.with_suffix(".aur")
    inp.write_bytes(payload)
    if out.exists():
        out.unlink()
    t0=time.perf_counter()
    subprocess.run(
        [str(cli),str(inp),str(out)],
        check=True,text=True,capture_output=True
    )
    elapsed=time.perf_counter()-t0
    size=out.stat().st_size
    inp.unlink(missing_ok=True)
    out.unlink(missing_ok=True)
    return size,elapsed


def main():
    if len(sys.argv)!=3:
        raise SystemExit(
            "usage: exp108_adaptive_word_dictionary.py "
            "NATIVE_K75_CLI NATIVE37_BLOB_CLI"
        )

    k75cli=Path(sys.argv[1]).resolve()
    n37cli=Path(sys.argv[2]).resolve()
    corpus=ROOT/"corpora"/"silesia"
    work=ROOT/"exp108_word_dictionary"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    total_raw=0
    current_archive_bytes=0
    potential_gain=0
    candidate_seconds=0.0
    text_entries=0
    winning_entries=0
    rows={}

    for name in FILES:
        src=corpus/name
        raw=src.read_bytes()
        total_raw+=len(raw)

        arc=work/f"{name}.kpf"
        subprocess.run(
            [str(k75cli),"c",str(src),str(arc),"1"],
            check=True,text=True,capture_output=True
        )
        current_archive_bytes+=arc.stat().st_size
        entries=parse_k75(extract_kpf_blob(arc))

        file_gain=0
        file_text=0
        file_wins=0
        top=[]

        for e in entries:
            chunk=raw[e["raw_offset"]:e["raw_offset"]+e["raw_size"]]
            if not E.is_text_like(chunk):
                continue
            text_entries+=1
            file_text+=1

            best=None
            for limit in (32,64,127):
                transformed,dictionary=wdt_encode(chunk,limit)
                assert wdt_decode(transformed)==chunk

                # Cheap pre-gate: only spend a backend encode if the transform
                # itself is plausibly useful.
                if len(transformed)+16>=len(chunk):
                    continue

                size,seconds=native37_size(
                    n37cli,
                    transformed,
                    work/f"wdt_{name}_{e['index']}_{limit}"
                )
                candidate_seconds+=seconds
                stored=9+size

                item={
                    "limit":limit,
                    "dictionary_entries":len(dictionary),
                    "transformed_bytes":len(transformed),
                    "compressed_bytes":size,
                    "stored_bytes":stored,
                }
                if best is None or stored<best["stored_bytes"]:
                    best=item

            if best is None:
                continue

            gain=e["stored_bytes"]-best["stored_bytes"]
            if gain>0:
                potential_gain+=gain
                file_gain+=gain
                winning_entries+=1
                file_wins+=1
                top.append({
                    "entry":e["index"],
                    "raw_bytes":e["raw_size"],
                    "current_mode":e["mode"],
                    "current_stored":e["stored_bytes"],
                    "gain":gain,
                    **best,
                })

        rows[name]={
            "raw_bytes":len(raw),
            "current_archive_bytes":arc.stat().st_size,
            "text_entries":file_text,
            "winning_entries":file_wins,
            "potential_gain_bytes":file_gain,
            "top_wins":sorted(top,key=lambda x:x["gain"],reverse=True)[:20],
        }

        print(
            "EXP105_FILE",name,
            "TEXT_ENTRIES",file_text,
            "WINS",file_wins,
            "GAIN",file_gain,
            flush=True
        )

    projected=current_archive_bytes-potential_gain
    result={
        "experiment":"EXP-108",
        "purpose":"adaptive-word-dictionary-transform-prototype",
        "raw_bytes":total_raw,
        "current_archive_bytes":current_archive_bytes,
        "current_ratio":current_archive_bytes/total_raw,
        "potential_gain_bytes":potential_gain,
        "projected_archive_bytes":projected,
        "projected_ratio":projected/total_raw,
        "text_entries":text_entries,
        "winning_entries":winning_entries,
        "candidate_backend_seconds":candidate_seconds,
        "files":rows,
    }

    Path("exp108_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    print("EXP105_AGGREGATE",json.dumps({
        k:result[k] for k in (
            "raw_bytes","current_archive_bytes","current_ratio",
            "potential_gain_bytes","projected_archive_bytes",
            "projected_ratio","text_entries","winning_entries",
            "candidate_backend_seconds"
        )
    },sort_keys=True),flush=True)
    print("EXP105_ROUNDTRIP_PASS",flush=True)


if __name__=="__main__":
    main()
