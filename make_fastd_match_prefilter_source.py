from pathlib import Path
import argparse

ap=argparse.ArgumentParser()
ap.add_argument("mode", choices=["baseline","tail8","tail8_mid8"])
ap.add_argument("--output", required=True)
args=ap.parse_args()

s=Path("KEPHIR_SPEED_D_SOURCE.cpp").read_text()

old='''                if(bestL>=8 && bestL<lim){
                    int mid=bestL>>1;
                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }
                }'''

tail8='''                if(bestL>=8 && bestL<lim){
                    int mid=bestL>>1;
                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }
                    uint64_t qtail,ptail;
                    memcpy(&qtail,d.data()+q+bestL-8,8);
                    memcpy(&ptail,d.data()+p+bestL-8,8);
                    if(qtail!=ptail){
                        bool stop=((depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));
                        if(K2_FUSED2_MODE==2 || K2_FUSED2_MODE==3){
                            double localSurprise=(bestL>=MINL)?dualLcost(p,min(bestL,32))/max(1,min(bestL,32)):LIT;
                            if(localSurprise>LIT+0.35 && depth<maxDepth-4) stop=false;
                        }
                        if(stop) break;
                        q=prev[q]; ++depth; continue;
                    }
                }'''

tail8_mid8='''                if(bestL>=8 && bestL<lim){
                    int mid=bestL>>1;
                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }
                    uint64_t qtail,ptail;
                    memcpy(&qtail,d.data()+q+bestL-8,8);
                    memcpy(&ptail,d.data()+p+bestL-8,8);
                    bool reject=(qtail!=ptail);
                    if(!reject && bestL>=16){
                        const int mo=mid-4;
                        uint64_t qmid,pmid;
                        memcpy(&qmid,d.data()+q+mo,8);
                        memcpy(&pmid,d.data()+p+mo,8);
                        reject=(qmid!=pmid);
                    }
                    if(reject){
                        bool stop=((depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));
                        if(K2_FUSED2_MODE==2 || K2_FUSED2_MODE==3){
                            double localSurprise=(bestL>=MINL)?dualLcost(p,min(bestL,32))/max(1,min(bestL,32)):LIT;
                            if(localSurprise>LIT+0.35 && depth<maxDepth-4) stop=false;
                        }
                        if(stop) break;
                        q=prev[q]; ++depth; continue;
                    }
                }'''

if s.count(old)!=1:
    raise SystemExit(f"PREFILTER_PATTERN_COUNT={s.count(old)}")

if args.mode=="tail8":
    s=s.replace(old,tail8,1)
elif args.mode=="tail8_mid8":
    s=s.replace(old,tail8_mid8,1)

Path(args.output).write_text(s)
print(f"FAST_D_PREFILTER_OK mode={args.mode} output={args.output} bytes={len(s)}")
