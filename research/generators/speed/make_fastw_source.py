from pathlib import Path
import os

p=Path("KEPHIR_FAST_U.cpp")
s=p.read_text()
mode=int(os.environ["FAST_W_MODE"])

old='''                bool stop=(l==lim || (depth>=1 && bestL>=128) || (depth>=3 && bestL>=64) || (depth>=7 && bestL>=32));'''

if mode==1:
    new='''                bool stop=(l==lim || (depth>=1 && bestL>=96) || (depth>=2 && bestL>=48) || (depth>=5 && bestL>=24));'''
elif mode==2:
    new='''                bool stop=(l==lim || (depth>=1 && bestL>=80) || (depth>=2 && bestL>=40) || (depth>=4 && bestL>=20));'''
else:
    raise SystemExit("BAD_MODE")

if old not in s: raise SystemExit("STOP_RULE_NOT_FOUND")
s=s.replace(old,new,1)
Path(f"KEPHIR_FAST_W{mode}.cpp").write_text(s)
print("FAST_W_READY",mode)
