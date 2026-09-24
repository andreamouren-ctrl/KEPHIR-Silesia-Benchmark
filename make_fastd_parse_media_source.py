from pathlib import Path
import os, re

src=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=src.read_text()
mode=int(os.environ.get("K2_MEDIA_LAZY_SKIP_MODE","0"))

# FAST-D parse media experiment:
# skip lazy p+1 match search only when the current match is already strong.
# mode 0 = baseline
# mode 1 = conservative: bestL >= 64
# mode 2 = balanced:     bestL >= 48
# mode 3 = aggressive:   bestL >= 32
limits={0:None,1:64,2:48,3:32}
if mode not in limits:
    raise SystemExit("BAD_MEDIA_LAZY_SKIP_MODE")

limit=limits[mode]
if limit is not None:
    pat=r'auto\s*\[\s*nL\s*,\s*nD\s*\]\s*=\s*findbest\s*\(\s*p\s*\+\s*1\s*,\s*localLazyDepth\s*\)\s*;'
    repl=(
        'pair<int,int> k2LazyCandidate={0,0}; '
        f'if(bestL<{limit}) k2LazyCandidate=findbest(p+1,localLazyDepth); '
        'auto [nL,nD]=k2LazyCandidate;'
    )
    s,n=re.subn(pat,repl,s,count=1)
    if n!=1:
        raise SystemExit(f"LAZY_FINDBEST_PATTERN_COUNT={n}")


Path("KEPHIR_SPEED_PARSE_MEDIA_SOURCE.cpp").write_text(s)
print("FAST_D_PARSE_MEDIA_PATCH_OK",mode,limit,len(s))
