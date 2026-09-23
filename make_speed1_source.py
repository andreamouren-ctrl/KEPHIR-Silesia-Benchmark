from pathlib import Path
import re

p=Path("KEPHIR_2_EXP39_FUSED2.cpp")
s=p.read_text()

def sub_const(name,value):
    global s
    pats=[
        rf'(constexpr\s+int\s+{name}\s*=\s*)\d+',
        rf'(constexpr\s+unsigned\s+{name}\s*=\s*)\d+',
        rf'(static\s+constexpr\s+int\s+{name}\s*=\s*)\d+',
        rf'(const\s+int\s+{name}\s*=\s*)\d+'
    ]
    for pat in pats:
        ns,n=re.subn(pat,rf'\g<1>{value}',s,count=1)
        if n:
            s=ns
            return True
    return False

for name,val in [("CHAIN_DEPTH",K2_CHAIN_DEPTH),("LAZY_DEPTH",K2_LAZY_DEPTH),("PRED_SAMPLE_MASK",K2_PRED_MASK)]:
    ok=sub_const(name,val)
    print(name,val,"patched",ok)

Path("KEPHIR_SPEED_SOURCE.cpp").write_text(s)
