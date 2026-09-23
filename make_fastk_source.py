from pathlib import Path
p=Path("KEPHIR_FAST_H.cpp")
s=p.read_text()
old='''if(dd>0 && dd<=W && q+3<n && h4(q)==hp){'''
new='''if(dd>0 && dd<=W && q+3<n && h4(q)==hp && (bestL<4 || bestL>=lim || d[(size_t)q+bestL]==d[(size_t)p+bestL])){'''
if old not in s:
    raise SystemExit("FAST_K_PREFILTER_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_K.cpp").write_text(s)
print("FAST_K_READY")
