from pathlib import Path
p=Path("KEPHIR_FAST_O.cpp")
s=p.read_text()
old='''                bool stop=(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));'''
new='''                bool stop=(l==lim || (depth>=1 && bestL>=128) || (depth>=3 && bestL>=64) || (depth>=7 && bestL>=32));'''
if old not in s: raise SystemExit("STOP_RULE_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_U.cpp").write_text(s)
print("FAST_U_AGGRESSIVE_STOP_READY")
