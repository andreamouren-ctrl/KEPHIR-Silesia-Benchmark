#!/usr/bin/env python3
from pathlib import Path
import json
import re
import sys

if len(sys.argv)!=2:
    raise SystemExit("usage: exp100_native37_source_audit.py GENERATED_CPP")

src=Path(sys.argv[1]).read_text()

patterns=[
    "static int compress_path",
    "int kephir37_cli_main",
    "compress_path(",
    "struct Chunk",
    "ch.comp",
    "Parallel BYTE-PERFECT",
    "K2_CHUNK_KIB",
]

out={"source_bytes":len(src.encode()),"snippets":{}}

for pat in patterns:
    positions=[m.start() for m in re.finditer(re.escape(pat),src)]
    snippets=[]
    for pos in positions[:12]:
        lo=max(0,pos-1200)
        hi=min(len(src),pos+5000)
        snippets.append(src[lo:hi])
    out["snippets"][pat]=snippets

Path("exp100_source_audit.json").write_text(
    json.dumps(out,indent=2)
)

for pat,snips in out["snippets"].items():
    print("EXP100_PATTERN",pat,"COUNT",len(snips),flush=True)
    for i,s in enumerate(snips[:4]):
        print(f"EXP100_SNIPPET_BEGIN {pat} {i}",flush=True)
        print(s,flush=True)
        print(f"EXP100_SNIPPET_END {pat} {i}",flush=True)

print("EXP100_AUDIT_COMPLETE",flush=True)
