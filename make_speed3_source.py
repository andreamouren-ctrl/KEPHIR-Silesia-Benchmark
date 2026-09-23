from pathlib import Path
import os
s=Path("KEPHIR_2_EXP39_FUSED2.cpp").read_text()
chain=int(os.environ["CHAIN"]); lazy=int(os.environ["LAZY"]); pred=int(os.environ.get("PRED","255"))
pairs=[
 ("#define CHAIN_DEPTH 42",f"#define CHAIN_DEPTH {chain}"),
 ("#define LAZY_DEPTH 19",f"#define LAZY_DEPTH {lazy}"),
 ("#define PRED_SAMPLE_MASK 31u",f"#define PRED_SAMPLE_MASK {pred}u"),
]
for old,new in pairs:
    if old not in s:
        raise SystemExit("PATCH_FAIL "+old)
    s=s.replace(old,new,1)
Path("KEPHIR_SPEED3.cpp").write_text(s)
print("PATCHED",chain,lazy,pred)
