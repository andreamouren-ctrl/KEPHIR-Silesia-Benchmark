from pathlib import Path
p=Path("KEPHIR_FAST_O.cpp")
s=p.read_text()
old="#define HASH_BITS 21"
new="#define HASH_BITS 22"
if old not in s: raise SystemExit("HASH_BITS_21_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_T.cpp").write_text(s)
print("FAST_T_HASH_BITS_22_READY")
