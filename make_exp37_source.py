from pathlib import Path
p=Path("KEPHIR_2_EXP33_DISTANCE_TOPOLOGY.cpp")
s=p.read_text()

anchor='#ifndef K2_DIST_TOPO_MODE\n#define K2_DIST_TOPO_MODE 0\n#endif'
insert='''\n#ifndef K2_DUAL_MATCH_MODE\n#define K2_DUAL_MATCH_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

# Build literal predictive prefix before match search so candidate ranking can use it.
needle='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
repl='''    const auto dualLitPref=k2_psg_literal_prefix_cost(d,LIT,K2_PSG_MODE);
    auto dualLcost=[&](int p,int len)->double{
        int e=min(n,p+len);
        return dualLitPref[(size_t)e]-dualLitPref[(size_t)p];
    };
    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
assert needle in s
s=s.replace(needle,repl,1)

# Add a second predictive-aware chain search after traditional findbest.
needle='''        return {bestL,bestD};
    };
    int prevTopoDist=0, prevTopoDist2=0;'''
insert2=r'''        return {bestL,bestD};
    };
    auto findpred=[&](int p,int maxDepth)->pair<int,int>{
        int bestL=0,bestD=0; double bestScore=-1e300;
        if(p+MINL>n) return {0,0};
        const uint32_t hp=h4(p);
        const int lim=min(MAXL,n-p);
        uint32_t ss=slot(hp), q=head[ss]; int depth=0;
        while(q!=NIL && depth<maxDepth){
            int dd=p-(int)q;
            if(dd>0 && dd<=W && q+3<n && h4(q)==hp){
                int l=4;
                while(l+8<=lim){
                    uint64_t a,b; memcpy(&a,d.data()+q+l,8); memcpy(&b,d.data()+p+l,8);
                    uint64_t x=a^b;
                    if(x){ l += (int)(__builtin_ctzll(x)>>3); break; }
                    l+=8;
                }
                while(l<lim && d[q+l]==d[p+l]) ++l;
                if(l>=MINL){
                    double lit=dualLcost(p,l);
                    double distPenalty=log2((double)dd+1.0);
                    double score=lit;
                    if(K2_DUAL_MATCH_MODE==1) score-=1.35*distPenalty;
                    else if(K2_DUAL_MATCH_MODE==2) score-=0.95*distPenalty;
                    else score-=0.65*distPenalty;
                    // Penalize very short alternatives so the second expert
                    // does not fragment the token stream.
                    if(l<8) score-=2.0;
                    if(score>bestScore){bestScore=score;bestL=l;bestD=dd;}
                }
            }
            q=prev[q]; ++depth;
        }
        if(bestL==MAXL && bestD>0){
            const int EXTMAX=65535; int q0=p-bestD; int l=bestL, elim=min(EXTMAX,n-p);
            while(l+8<=elim){ uint64_t a,b; memcpy(&a,d.data()+q0+l,8); memcpy(&b,d.data()+p+l,8); uint64_t x=a^b; if(x){l+=(int)(__builtin_ctzll(x)>>3);break;} l+=8; }
            while(l<elim && d[q0+l]==d[p+l])++l; bestL=l;
        }
        return {bestL,bestD};
    };
    int prevTopoDist=0, prevTopoDist2=0;'''
assert needle in s
s=s.replace(needle,insert2,1)

# Avoid computing PSG prefix twice; reuse early prefix as parser lcost field.
old='''    const auto litPref=k2_psg_literal_prefix_cost(d,LIT,K2_PSG_MODE);
    auto lcost=[&](int p,int len)->double{
        int e=min(n,p+len);
        return litPref[(size_t)e]-litPref[(size_t)p];
    };'''
new='''    auto lcost=[&](int p,int len)->double{
        return dualLcost(p,len);
    };'''
assert old in s
s=s.replace(old,new,1)

# At each position, evaluate traditional and predictive candidates using the same final cost.
old='''        auto [bestL,bestD]=findbest(p,CHAIN_DEPTH);
        bool take=bestL>=MINL && mcost(bestL,bestD)<lcost(p,bestL);'''
new='''        auto [bestL,bestD]=findbest(p,CHAIN_DEPTH);
        if(K2_DUAL_MATCH_MODE){
            auto [pL,pD]=findpred(p,CHAIN_DEPTH);
            if(pL>=MINL){
                double baseGain=bestL>=MINL ? lcost(p,bestL)-mcost(bestL,bestD) : -1e300;
                double predGain=lcost(p,pL)-mcost(pL,pD);
                double gate=(K2_DUAL_MATCH_MODE==1?0.30:(K2_DUAL_MATCH_MODE==2?0.0:-0.20));
                if(predGain>baseGain+gate){
                    if(K2_DUAL_MATCH_MODE!=1 || pL+2>=bestL){bestL=pL;bestD=pD;}
                }
            }
        }
        bool take=bestL>=MINL && mcost(bestL,bestD)<lcost(p,bestL);'''
assert old in s
s=s.replace(old,new,1)

# Let lazy look-ahead use the same dual expert.
old='''            auto [nL,nD]=findbest(p+1,localLazyDepth);
            if(nL>=MINL){'''
new='''            auto [nL,nD]=findbest(p+1,localLazyDepth);
            if(K2_DUAL_MATCH_MODE){
                auto [qL,qD]=findpred(p+1,localLazyDepth);
                if(qL>=MINL){
                    double g0=nL>=MINL?lcost(p+1,nL)-mcost(nL,nD):-1e300;
                    double g1=lcost(p+1,qL)-mcost(qL,qD);
                    if(g1>g0){nL=qL;nD=qD;}
                }
            }
            if(nL>=MINL){'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp").write_text(s)
print("EXP37_SOURCE_BYTES",len(s.encode()))
