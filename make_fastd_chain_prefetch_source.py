from pathlib import Path
import argparse
ap=argparse.ArgumentParser()
ap.add_argument("mode",choices=["baseline","prefetch"])
ap.add_argument("--output",required=True)
args=ap.parse_args()
s=Path("KEPHIR_SPEED_D_SOURCE.cpp").read_text()

sig='''        while(q!=NIL && depth<maxDepth){'''

if args.mode=="prefetch":
    fb=s.index("auto findbest=")
    start=s.index(sig,fb)
    end=s.index('''        if(bestL==MAXL && bestD>0){''',start)
    body=s[start:end]
    body=body.replace(sig,'''        while(q!=NIL && depth<maxDepth){
            const uint32_t pfq=prev[q];
            if(pfq!=NIL){
                __builtin_prefetch(prev+pfq,0,1);
                __builtin_prefetch(d.data()+pfq,0,1);
            }''',1)
    s=s[:start]+body+s[end:]
    print("PREFETCH_HINT_ONLY")

Path(args.output).write_text(s)
print("FAST_D_CHAIN_PREFETCH_OK",args.mode,len(s))
