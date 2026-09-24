from pathlib import Path
import re, os

p=Path("KEPHIR_2_EXP39_FUSED2.cpp")
s=p.read_text()

chain=int(os.environ.get("K2_CHAIN_DEPTH_VALUE","24"))
lazy=int(os.environ.get("K2_LAZY_DEPTH_VALUE","12"))
pred=int(os.environ.get("K2_PRED_MASK_VALUE","63"))

repls=[
    (r'(#define\s+CHAIN_DEPTH\s+)\d+', rf'\g<1>{chain}'),
    (r'(#define\s+LAZY_DEPTH\s+)\d+', rf'\g<1>{lazy}'),
    (r'(#define\s+PRED_SAMPLE_MASK\s+)\d+u?', rf'\g<1>{pred}u'),
]
for pat,repl in repls:
    s,n=re.subn(pat,repl,s,count=1)
    if n!=1:
        raise SystemExit(f"PATCH_FAIL {pat}")
print("PATCHED",chain,lazy,pred)
Path("KEPHIR_SPEED_SOURCE.cpp").write_text(s)
