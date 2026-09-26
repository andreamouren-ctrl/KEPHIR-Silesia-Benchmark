from pathlib import Path
import os, re

src=Path(os.environ.get("AURORA_EXP37_BASE","EXP37_BASE.cpp"))
dst=Path(os.environ.get("AURORA_EXP37_OUT","KEPHIR_2_EXP37_DUAL_MATCH.cpp"))
chain=int(os.environ["AURORA_CHAIN_DEPTH"])
lazy=int(os.environ["AURORA_LAZY_DEPTH"])

s=src.read_text()
orig_chain=re.search(r'#define\s+CHAIN_DEPTH\s+(\d+)',s)
orig_lazy=re.search(r'#define\s+LAZY_DEPTH\s+(\d+)',s)
if not orig_chain or not orig_lazy:
    raise SystemExit("EXP37 depth constants not found")

s,n1=re.subn(r'(#define\s+CHAIN_DEPTH\s+)\d+',rf'\g<1>{chain}',s,count=1)
s,n2=re.subn(r'(#define\s+LAZY_DEPTH\s+)\d+',rf'\g<1>{lazy}',s,count=1)
if n1!=1 or n2!=1:
    raise SystemExit("EXP37 depth patch failed")

dst.write_text(s)
print(
    "AURORA_MEDIA_DEPTH_SOURCE",
    "original_chain",orig_chain.group(1),
    "original_lazy",orig_lazy.group(1),
    "chain",chain,
    "lazy",lazy,
    "bytes",len(s.encode()),
)
