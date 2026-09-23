from pathlib import Path
import re, os

p=Path("KEPHIR_2_EXP39_FUSED2.cpp")
s=p.read_text()

chain=int(os.environ.get("K2_CHAIN_DEPTH_VALUE","24"))
lazy=int(os.environ.get("K2_LAZY_DEPTH_VALUE","12"))
pred=int(os.environ.get("K2_PRED_MASK_VALUE","63"))

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
            print(name,value,"patched")
            return True
    print(name,value,"NOT_FOUND")
    return False

sub_const("CHAIN_DEPTH",chain)
sub_const("LAZY_DEPTH",lazy)
sub_const("PRED_SAMPLE_MASK",pred)
Path("KEPHIR_SPEED_SOURCE.cpp").write_text(s)
