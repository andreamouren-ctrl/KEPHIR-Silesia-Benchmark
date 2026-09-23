from pathlib import Path
import re
p=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=p.read_text()

# Exact-output parser acceleration:
# if current candidate already differs at bestL, it cannot beat bestL.
pat=r'(if\(dd>0 && dd<=W && q\+3<n && h4\(q\)==hp\)\{\s*)(int l=4;)'
repl=r'''\1
                if(bestL>=4 && bestL<lim && q+bestL<n && d[(size_t)q+bestL]!=d[(size_t)p+bestL]){
                    q=prev[q]; ++depth; continue;
                }
                \2'''
s,n=re.subn(pat,repl,s,count=1)
print("FAST_J_PREFILTER_PATCHED",n)
if n!=1: raise SystemExit("FAST_J_PATTERN_NOT_FOUND")
Path("KEPHIR_FAST_J.cpp").write_text(s)
