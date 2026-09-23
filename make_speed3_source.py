from pathlib import Path
import re,os
s=Path("KEPHIR_2_EXP39_FUSED2.cpp").read_text()
chain=int(os.environ["CHAIN"]); lazy=int(os.environ["LAZY"]); pred=int(os.environ.get("PRED","255"))
for pat,repl in [
 (r'(#define\\s+CHAIN_DEPTH\\s+)\\d+',rf'\\g<1>{chain}'),
 (r'(#define\\s+LAZY_DEPTH\\s+)\\d+',rf'\\g<1>{lazy}'),
 (r'(#define\\s+PRED_SAMPLE_MASK\\s+)\\d+u?',rf'\\g<1>{pred}u')]:
 s,n=re.subn(pat,repl,s,count=1)
 if n!=1: raise SystemExit("PATCH_FAIL "+pat)
Path("KEPHIR_SPEED3.cpp").write_text(s)
print("PATCHED",chain,lazy,pred)
