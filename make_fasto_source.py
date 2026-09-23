from pathlib import Path
p=Path("KEPHIR_FAST_K.cpp")
s=p.read_text()
old='#define HASH_BITS 20'
new='#define HASH_BITS 21'
if old not in s: raise SystemExit("HASH_BITS_20_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_O.cpp").write_text(s)
print("FAST_O_HASH_BITS_21_READY")
