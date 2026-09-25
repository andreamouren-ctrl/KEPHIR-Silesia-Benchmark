from pathlib import Path
import re

src=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=src.read_text()

anchor=re.search(r'(^|\n)([^\n]*\bparse\s*\([^\n]*\)\s*\{)',s)
if not anchor:
    raise SystemExit("PARSE_ANCHOR_NOT_FOUND")
insert='\nthread_local int k2_runtime_chain_depth=48;\nthread_local int k2_runtime_lazy_depth=24;\n'
pos=anchor.start(2)
s=s[:pos]+insert+s[pos:]

pairs=[
    ('const int localLazyDepth=k2_lazy_depth(d,K2_LAZY_MODE);',
     'const int localLazyDepth=k2_runtime_lazy_depth;'),
    ('findbest(p,CHAIN_DEPTH)','findbest(p,k2_runtime_chain_depth)'),
    ('findpred(p,CHAIN_DEPTH)','findpred(p,k2_runtime_chain_depth)'),
]
for old,new in pairs:
    if old not in s:
        raise SystemExit("RUNTIME_DEPTH_PATTERN_NOT_FOUND "+old)
    s=s.replace(old,new)

Path("KEPHIR_SPEED_D_RUNTIME_SOURCE.cpp").write_text(s)
print("FAST_D_RUNTIME_DEPTH_OK",len(s))
