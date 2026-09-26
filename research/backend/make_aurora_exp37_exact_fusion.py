from pathlib import Path

src=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
dst=Path("KEPHIR_2_EXP37_EXACT_FUSED.cpp")
s=src.read_text()

anchor='#ifndef K2_DUAL_MATCH_MODE\n#define K2_DUAL_MATCH_MODE 0\n#endif'
insert='''\n#ifndef K2_EXACT_FUSED_MATCH_MODE\n#define K2_EXACT_FUSED_MATCH_MODE 0\n#endif\n'''
if anchor not in s:
    raise SystemExit("DUAL_MODE_ANCHOR_NOT_FOUND")
s=s.replace(anchor,anchor+insert,1)

needle='''        return {bestL,bestD};
    };
    int prevTopoDist=0, prevTopoDist2=0;'''
if needle not in s:
    raise SystemExit("FINDPRED_END_NOT_FOUND")

fused=r'''        return {bestL,bestD};
    };

    struct K2ExactDualResult {
        int bestL,bestD,predL,predD;
    };

    auto finddual_exact=[&](int p,int maxDepth)->K2ExactDualResult{
        int bestL=0,bestD=0,predL=0,predD=0;
        double predScore=-1e300;
        if(p+MINL>n) return {0,0,0,0};

        const uint32_t hp=h4(p);
        const int lim=min(MAXL,n-p);
        uint32_t ss=slot(hp), q=head[ss];
        int depth=0;
        bool traditionalActive=true;

        while(q!=NIL && depth<maxDepth){
            int dd=p-(int)q;
            if(dd>0 && dd<=W && q+3<n && h4(q)==hp){
                int l=4;
                while(l+8<=lim){
                    uint64_t a,b;
                    memcpy(&a,d.data()+q+l,8);
                    memcpy(&b,d.data()+p+l,8);
                    uint64_t x=a^b;
                    if(x){ l += (int)(__builtin_ctzll(x)>>3); break; }
                    l+=8;
                }
                while(l<lim && d[q+l]==d[p+l]) ++l;

                if(traditionalActive && l>bestL){
                    bestL=l;
                    bestD=dd;
                }

                if(l>=MINL){
                    double lit=dualLcost(p,l);
                    double distPenalty=log2((double)dd+1.0);
                    double score=lit;
                    if(K2_DUAL_MATCH_MODE==1) score-=1.35*distPenalty;
                    else if(K2_DUAL_MATCH_MODE==2) score-=0.95*distPenalty;
                    else score-=0.65*distPenalty;
                    if(l<8) score-=2.0;
                    if(score>predScore){
                        predScore=score;
                        predL=l;
                        predD=dd;
                    }
                }

                if(traditionalActive &&
                   (l==lim ||
                    (depth>=7 && bestL>=128) ||
                    (depth>=15 && bestL>=64) ||
                    (depth>=31 && bestL>=32))){
                    // Freeze the traditional result exactly where the original
                    // findbest() would have broken. Continue only because the
                    // separate historical findpred() would still traverse.
                    traditionalActive=false;
                }
            }
            q=prev[q];
            ++depth;
        }

        if(bestL==MAXL && bestD>0){
            const int EXTMAX=65535;
            int q0=p-bestD;
            int l=bestL, elim=min(EXTMAX,n-p);
            while(l+8<=elim){
                uint64_t a,b;
                memcpy(&a,d.data()+q0+l,8);
                memcpy(&b,d.data()+p+l,8);
                uint64_t x=a^b;
                if(x){ l+=(int)(__builtin_ctzll(x)>>3); break; }
                l+=8;
            }
            while(l<elim && d[q0+l]==d[p+l]) ++l;
            bestL=l;
        }

        if(predL==MAXL && predD>0){
            const int EXTMAX=65535;
            int q0=p-predD;
            int l=predL, elim=min(EXTMAX,n-p);
            while(l+8<=elim){
                uint64_t a,b;
                memcpy(&a,d.data()+q0+l,8);
                memcpy(&b,d.data()+p+l,8);
                uint64_t x=a^b;
                if(x){ l+=(int)(__builtin_ctzll(x)>>3); break; }
                l+=8;
            }
            while(l<elim && d[q0+l]==d[p+l]) ++l;
            predL=l;
        }

        return {bestL,bestD,predL,predD};
    };

    int prevTopoDist=0, prevTopoDist2=0;'''
s=s.replace(needle,fused,1)

old='''        auto [bestL,bestD]=findbest(p,CHAIN_DEPTH);
        if(K2_DUAL_MATCH_MODE){
            auto [pL,pD]=findpred(p,CHAIN_DEPTH);
            if(pL>=MINL){'''
new='''        int bestL=0,bestD=0,pL=0,pD=0;
        if(K2_DUAL_MATCH_MODE && K2_EXACT_FUSED_MATCH_MODE){
            auto z=finddual_exact(p,CHAIN_DEPTH);
            bestL=z.bestL; bestD=z.bestD; pL=z.predL; pD=z.predD;
        } else {
            tie(bestL,bestD)=findbest(p,CHAIN_DEPTH);
            if(K2_DUAL_MATCH_MODE) tie(pL,pD)=findpred(p,CHAIN_DEPTH);
        }
        if(K2_DUAL_MATCH_MODE){
            if(pL>=MINL){'''
if old not in s:
    raise SystemExit("MAIN_DUAL_CALL_NOT_FOUND")
s=s.replace(old,new,1)

old='''            auto [nL,nD]=findbest(p+1,localLazyDepth);
            if(K2_DUAL_MATCH_MODE){
                auto [qL,qD]=findpred(p+1,localLazyDepth);
                if(qL>=MINL){'''
new='''            int nL=0,nD=0,qL=0,qD=0;
            if(K2_DUAL_MATCH_MODE && K2_EXACT_FUSED_MATCH_MODE){
                auto z=finddual_exact(p+1,localLazyDepth);
                nL=z.bestL; nD=z.bestD; qL=z.predL; qD=z.predD;
            } else {
                tie(nL,nD)=findbest(p+1,localLazyDepth);
                if(K2_DUAL_MATCH_MODE) tie(qL,qD)=findpred(p+1,localLazyDepth);
            }
            if(K2_DUAL_MATCH_MODE){
                if(qL>=MINL){'''
if old not in s:
    raise SystemExit("LAZY_DUAL_CALL_NOT_FOUND")
s=s.replace(old,new,1)

dst.write_text(s)
print("AURORA_EXP37_EXACT_FUSION_SOURCE_BYTES",len(s.encode()))
