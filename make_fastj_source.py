from pathlib import Path
p=Path("KEPHIR_FAST_H.cpp")
s=p.read_text()
old='''bool stop=(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));'''
new='''bool stop=(l==lim || (depth>=3 && bestL>=128) || (depth>=7 && bestL>=64) || (depth>=15 && bestL>=32));'''
if old not in s:
    raise SystemExit("FAST_J_EARLY_STOP_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_J.cpp").write_text(s)
print("FAST_J_READY")
