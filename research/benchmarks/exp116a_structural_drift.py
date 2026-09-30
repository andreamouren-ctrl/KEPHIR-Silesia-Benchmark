#!/usr/bin/env python3
"""
EXP-116A — Structural Drift / Long-Range Redundancy Study

Research-only diagnostic.

EXP-115 found one harmful external adaptive-context choice (world192.txt)
and one small missed opportunity (Calgary book2). This study extracts richer
features from the SAME bounded 256 KiB sample budget used by EXP-114:
- quarter entropy spread;
- quarter and window histogram drift;
- printable/zero/byte-mean ranges;
- window entropy variance;
- distant 4-byte and 8-byte shingle overlap.

No compressor setting is changed. The objective is to identify a cheap
content signal that rejects heterogeneous long streams such as world192
without rejecting known profitable long-context cases.
"""

from pathlib import Path
import hashlib
import itertools
import json
import math
import statistics
import sys

ROOT=Path.cwd()
MiB=1024*1024
WINDOWS_PER_QUARTER=8
WINDOW_BYTES=8*1024

SILESIA_ORACLE={
    "dickens":"ctx8m",
    "mozilla":"baseline",
    "mr":"baseline",
    "nci":"ctx8m",
    "ooffice":"ctx4m",
    "osdb":"ctx8m",
    "reymont":"baseline",
    "samba":"baseline",
    "sao":"ctx8m",
    "webster":"ctx8m",
    "x-ray":"baseline",
    "xml":"baseline",
}

EXTERNAL_ORACLE={
    "canterbury":{
        "alice29.txt":"baseline","asyoulik.txt":"baseline","cp.html":"baseline",
        "fields.c":"baseline","grammar.lsp":"baseline","kennedy.xls":"baseline",
        "lcet10.txt":"baseline","plrabn12.txt":"baseline","ptt5":"baseline",
        "sum":"baseline","xargs.1":"baseline",
    },
    "calgary":{
        "bib":"baseline","book1":"ctx4m","book2":"ctx4m","geo":"baseline",
        "news":"baseline","obj1":"baseline","obj2":"baseline","paper1":"baseline",
        "paper2":"baseline","paper3":"baseline","paper4":"baseline",
        "paper5":"baseline","paper6":"baseline","pic":"baseline",
        "progc":"baseline","progl":"baseline","progp":"baseline","trans":"baseline",
    },
    "large":{
        "E.coli":"ctx8m","bible.txt":"ctx4m","world192.txt":"baseline",
    },
}


def entropy(buf):
    if not buf:
        return 0.0
    counts=[0]*256
    for b in buf:
        counts[b]+=1
    n=len(buf)
    return -sum(
        (c/n)*math.log2(c/n)
        for c in counts if c
    )


def histogram(buf):
    counts=[0]*256
    for b in buf:
        counts[b]+=1
    n=max(1,len(buf))
    return [c/n for c in counts]


def tv(a,b):
    return 0.5*sum(abs(x-y) for x,y in zip(a,b))


def printable_fraction(buf):
    if not buf:
        return 0.0
    return sum(
        b in (9,10,13) or 32<=b<127 for b in buf
    )/len(buf)


def zero_fraction(buf):
    return buf.count(0)/max(1,len(buf))


def byte_mean(buf):
    return sum(buf)/max(1,len(buf))


def shingle_set(buf,width,step=4):
    if len(buf)<width:
        return set()
    out=set()
    for i in range(0,len(buf)-width+1,step):
        # deterministic compact token; digest avoids retaining large byte slices
        out.add(hashlib.blake2s(
            buf[i:i+width],digest_size=8
        ).digest())
    return out


def jaccard(a,b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b)/len(a | b)


def bounded_windows(path):
    data=path.read_bytes()
    quarters=[]
    flat=[]

    for q in range(4):
        begin=(len(data)*q)//4
        end=(len(data)*(q+1))//4
        length=end-begin
        qwins=[]

        for part in range(WINDOWS_PER_QUARTER):
            rb=begin+(length*part)//WINDOWS_PER_QUARTER
            re=begin+(length*(part+1))//WINDOWS_PER_QUARTER
            if re<=rb:
                continue
            want=min(WINDOW_BYTES,re-rb)
            off=rb+(re-rb-want)//2
            buf=data[off:off+want]
            qwins.append(buf)
            flat.append(buf)

        quarters.append(qwins)
    return quarters,flat


def feature_file(path):
    quarters,windows=bounded_windows(path)
    sampled_bytes=sum(len(w) for w in windows)

    qbufs=[b"".join(q) for q in quarters]
    qentropy=[entropy(q) for q in qbufs]
    qhist=[histogram(q) for q in qbufs]
    qprint=[printable_fraction(q) for q in qbufs]
    qzero=[zero_fraction(q) for q in qbufs]
    qmean=[byte_mean(q) for q in qbufs]

    qtv=[
        tv(qhist[i],qhist[j])
        for i,j in itertools.combinations(range(len(qhist)),2)
    ]

    wentropy=[entropy(w) for w in windows]
    whist=[histogram(w) for w in windows]
    wprint=[printable_fraction(w) for w in windows]
    wzero=[zero_fraction(w) for w in windows]

    adjacent_tv=[
        tv(whist[i],whist[i+1])
        for i in range(len(whist)-1)
    ]
    cross_quarter_tv=[]
    for qi in range(3):
        if quarters[qi] and quarters[qi+1]:
            a=histogram(quarters[qi][-1])
            b=histogram(quarters[qi+1][0])
            cross_quarter_tv.append(tv(a,b))

    shingles4=[shingle_set(q,4) for q in qbufs]
    shingles8=[shingle_set(q,8) for q in qbufs]
    jac4=[jaccard(shingles4[i],shingles4[j])
          for i,j in itertools.combinations(range(4),2)]
    jac8=[jaccard(shingles8[i],shingles8[j])
          for i,j in itertools.combinations(range(4),2)]

    all_sample=b"".join(windows)

    return {
        "raw_bytes":path.stat().st_size,
        "sampled_bytes":sampled_bytes,
        "sample_entropy":entropy(all_sample),
        "sample_printable":printable_fraction(all_sample),
        "sample_zero":zero_fraction(all_sample),
        "quarter_entropy_spread":max(qentropy)-min(qentropy) if qentropy else 0.0,
        "quarter_tv_max":max(qtv) if qtv else 0.0,
        "quarter_tv_mean":statistics.fmean(qtv) if qtv else 0.0,
        "quarter_printable_range":max(qprint)-min(qprint) if qprint else 0.0,
        "quarter_zero_range":max(qzero)-min(qzero) if qzero else 0.0,
        "quarter_byte_mean_range":max(qmean)-min(qmean) if qmean else 0.0,
        "window_entropy_range":max(wentropy)-min(wentropy) if wentropy else 0.0,
        "window_entropy_std":statistics.pstdev(wentropy) if len(wentropy)>1 else 0.0,
        "adjacent_window_tv_max":max(adjacent_tv) if adjacent_tv else 0.0,
        "adjacent_window_tv_mean":statistics.fmean(adjacent_tv) if adjacent_tv else 0.0,
        "boundary_window_tv_max":max(cross_quarter_tv) if cross_quarter_tv else 0.0,
        "window_printable_range":max(wprint)-min(wprint) if wprint else 0.0,
        "window_zero_range":max(wzero)-min(wzero) if wzero else 0.0,
        "quarter_shingle4_jaccard_min":min(jac4) if jac4 else 0.0,
        "quarter_shingle4_jaccard_mean":statistics.fmean(jac4) if jac4 else 0.0,
        "quarter_shingle8_jaccard_min":min(jac8) if jac8 else 0.0,
        "quarter_shingle8_jaccard_mean":statistics.fmean(jac8) if jac8 else 0.0,
    }


def add_dataset(rows,dataset,root,oracle):
    for name,label in oracle.items():
        path=root/name
        feat=feature_file(path)
        row={
            "dataset":dataset,
            "file":name,
            "oracle":label,
            "features":feat,
        }
        rows.append(row)
        print(
            "EXP116A_FILE",dataset,name,
            "ORACLE",label,
            "RAW",feat["raw_bytes"],
            "SPREAD",feat["quarter_entropy_spread"],
            "QTV",feat["quarter_tv_max"],
            "WTV",feat["adjacent_window_tv_max"],
            "WSTD",feat["window_entropy_std"],
            "J4",feat["quarter_shingle4_jaccard_mean"],
            "J8",feat["quarter_shingle8_jaccard_mean"],
            "PRINT",feat["sample_printable"],
            flush=True,
        )


def main():
    rows=[]
    add_dataset(
        rows,"silesia",ROOT/"corpora"/"silesia",SILESIA_ORACLE
    )
    for dataset,oracle in EXTERNAL_ORACLE.items():
        add_dataset(
            rows,dataset,ROOT/"corpora"/dataset,oracle
        )

    targets=[
        r for r in rows
        if (r["dataset"],r["file"]) in {
            ("large","world192.txt"),
            ("calgary","book2"),
            ("silesia","dickens"),
            ("silesia","ooffice"),
            ("silesia","reymont"),
            ("large","E.coli"),
            ("large","bible.txt"),
            ("calgary","book1"),
        }
    ]

    result={
        "experiment":"EXP-116A",
        "purpose":"structural-drift-long-range-redundancy-study",
        "sample_budget_max_bytes":256*1024,
        "rows":rows,
        "targets":targets,
    }
    Path("exp116a_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)
    )

    assert len(rows)==44
    assert all(r["features"]["sampled_bytes"]<=256*1024 for r in rows)
    print("EXP116A_COMPLETE ROWS",len(rows),flush=True)


if __name__=="__main__":
    main()
