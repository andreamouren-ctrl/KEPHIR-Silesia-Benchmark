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
            const uint32_t nextq=prev[q];
            if(nextq!=NIL){
                __builtin_prefetch(prev+nextq,0,1);
                __builtin_prefetch(d.data()+nextq,0,1);
            }''',1)
    n=body.count("q=prev[q]")
    if n<1: raise SystemExit("NO_NEXT_ASSIGNMENTS")
    body=body.replace("q=prev[q]","q=nextq")
    s=s[:start]+body+s[end:]
    print("PREFETCH_REPLACED",n)

Path(args.output).write_text(s)
print("FAST_D_CHAIN_PREFETCH_OK",args.mode,len(s))
