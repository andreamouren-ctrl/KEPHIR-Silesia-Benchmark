from pathlib import Path
import argparse
ap=argparse.ArgumentParser()
ap.add_argument("mode",choices=["baseline","prefix8"])
ap.add_argument("--output",required=True)
args=ap.parse_args()
s=Path("KEPHIR_SPEED_D_SOURCE.cpp").read_text()

old='''                if(bestL>=8 && bestL<lim){
                    int mid=bestL>>1;
                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }
                }'''

new='''                if(bestL>=8 && bestL<lim){
                    int mid=bestL>>1;
                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }
                    uint64_t qp,pp;
                    memcpy(&qp,d.data()+q,8);
                    memcpy(&pp,d.data()+p,8);
                    if(qp!=pp){
                        bool stop=((depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));
                        if(stop) break;
                        q=prev[q]; ++depth; continue;
                    }
                }'''

if s.count(old)!=1:
    raise SystemExit(f"PREFIX8_PATTERN_COUNT={s.count(old)}")
if args.mode=="prefix8":
    s=s.replace(old,new,1)
Path(args.output).write_text(s)
print("FAST_D_PREFIX8_OK",args.mode,len(s))
