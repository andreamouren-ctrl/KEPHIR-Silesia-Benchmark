from pathlib import Path
p=Path("KEPHIR_2_EXP38_FUSED_DUAL.cpp")
s=p.read_text()

anchor='#ifndef K2_FUSED_MATCH_MODE\n#define K2_FUSED_MATCH_MODE 0\n#endif'
insert='''\n#ifndef K2_FUSED2_MODE\n#define K2_FUSED2_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

# finder state
old='''        int bestL=0,bestD=0,predL=0,predD=0;
        double predScore=-1e300;'''
new='''        int bestL=0,bestD=0,predL=0,predD=0,predL2=0,predD2=0;
        double predScore=-1e300,predScore2=-1e300;'''
assert old in s
s=s.replace(old,new,1)

# candidate ranking and early stop
old='''                    if(score>predScore){predScore=score;predL=l;predD=dd;}
                }
                if(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32)) break;'''
new='''                    if(score>predScore){
                        predScore2=predScore; predL2=predL; predD2=predD;
                        predScore=score; predL=l; predD=dd;
                    } else if(K2_FUSED2_MODE && score>predScore2){
                        predScore2=score; predL2=l; predD2=dd;
                    }
                }
                bool stop=(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));
                if(K2_FUSED2_MODE==2 || K2_FUSED2_MODE==3){
                    double localSurprise=(bestL>=MINL)?dualLcost(p,min(bestL,32))/max(1,min(bestL,32)):LIT;
                    if(localSurprise>LIT+0.35 && depth<maxDepth-4) stop=false;
                }
                if(stop) break;'''
assert old in s
s=s.replace(old,new,1)

# after first candidate comparison, compare second candidate too
old='''        if(K2_FUSED_MATCH_MODE && predL>=MINL){
            auto localCost=[&](int len,int dist)->double{
                return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
            };
            double g0=bestL>=MINL?dualLcost(p,bestL)-localCost(bestL,bestD):-1e300;
            double g1=dualLcost(p,predL)-localCost(predL,predD);
            double gate=(K2_FUSED_MATCH_MODE==1?0.30:(K2_FUSED_MATCH_MODE==2?0.0:0.15));
            if(g1>g0+gate && (K2_FUSED_MATCH_MODE!=1 || predL+2>=bestL)){bestL=predL;bestD=predD;}
        }'''
new='''        if(K2_FUSED_MATCH_MODE && predL>=MINL){
            auto localCost=[&](int len,int dist)->double{
                return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
            };
            double g0=bestL>=MINL?dualLcost(p,bestL)-localCost(bestL,bestD):-1e300;
            double g1=dualLcost(p,predL)-localCost(predL,predD);
            double gate=(K2_FUSED_MATCH_MODE==1?0.30:(K2_FUSED_MATCH_MODE==2?0.0:0.15));
            if(g1>g0+gate && (K2_FUSED_MATCH_MODE!=1 || predL+2>=bestL)){bestL=predL;bestD=predD;g0=g1;}
            if((K2_FUSED2_MODE==1 || K2_FUSED2_MODE==3) && predL2>=MINL){
                double g2=dualLcost(p,predL2)-localCost(predL2,predD2);
                if(g2>g0+0.12 && predL2+3>=bestL){bestL=predL2;bestD=predD2;}
            }
        }'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP39_FUSED2.cpp").write_text(s)
print("EXP39_SOURCE_BYTES",len(s.encode()))
