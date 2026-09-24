from pathlib import Path
p=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
s=p.read_text()

# Add fused mode.
anchor='#ifndef K2_DUAL_MATCH_MODE\n#define K2_DUAL_MATCH_MODE 0\n#endif'
insert='''\n#ifndef K2_FUSED_MATCH_MODE\n#define K2_FUSED_MATCH_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

# Extend traditional finder so it also tracks a predictive candidate in the same traversal.
old='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{
        int bestL=0,bestD=0;
        if(p+MINL>n) return {0,0};'''
new='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{
        int bestL=0,bestD=0,predL=0,predD=0;
        double predScore=-1e300;
        if(p+MINL>n) return {0,0};'''
assert old in s
s=s.replace(old,new,1)

old='''                if(l>bestL){bestL=l;bestD=dd;}
                if(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32)) break;'''
new='''                if(l>bestL){bestL=l;bestD=dd;}
                if(K2_FUSED_MATCH_MODE && l>=MINL){
                    double lit=dualLcost(p,l);
                    double dp=log2((double)dd+1.0);
                    double score=lit-(K2_FUSED_MATCH_MODE==1?1.35:(K2_FUSED_MATCH_MODE==2?0.95:0.75))*dp;
                    if(l<8) score-=2.0;
                    if(score>predScore){predScore=score;predL=l;predD=dd;}
                }
                if(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32)) break;'''
assert old in s
s=s.replace(old,new,1)

# After traditional long-match extension, compare fused candidate against longest using the same real parser gain.
old='''        if(bestL==MAXL && bestD>0){
            const int EXTMAX=65535; int q0=p-bestD; int l=bestL, elim=min(EXTMAX,n-p);
            while(l+8<=elim){ uint64_t a,b; memcpy(&a,d.data()+q0+l,8); memcpy(&b,d.data()+p+l,8); uint64_t x=a^b; if(x){l+=(int)(__builtin_ctzll(x)>>3);break;} l+=8; }
            while(l<elim && d[q0+l]==d[p+l])++l; bestL=l;
        }
        return {bestL,bestD};'''
new='''        if(bestL==MAXL && bestD>0){
            const int EXTMAX=65535; int q0=p-bestD; int l=bestL, elim=min(EXTMAX,n-p);
            while(l+8<=elim){ uint64_t a,b; memcpy(&a,d.data()+q0+l,8); memcpy(&b,d.data()+p+l,8); uint64_t x=a^b; if(x){l+=(int)(__builtin_ctzll(x)>>3);break;} l+=8; }
            while(l<elim && d[q0+l]==d[p+l])++l; bestL=l;
        }
        if(K2_FUSED_MATCH_MODE && predL>=MINL){
            auto localCost=[&](int len,int dist)->double{
                return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
            };
            double g0=bestL>=MINL?dualLcost(p,bestL)-localCost(bestL,bestD):-1e300;
            double g1=dualLcost(p,predL)-localCost(predL,predD);
            double gate=(K2_FUSED_MATCH_MODE==1?0.30:(K2_FUSED_MATCH_MODE==2?0.0:0.15));
            if(g1>g0+gate && (K2_FUSED_MATCH_MODE!=1 || predL+2>=bestL)){bestL=predL;bestD=predD;}
        }
        return {bestL,bestD};'''
assert old in s
s=s.replace(old,new,1)

# Disable second traversal when fused mode is active.
old='''        if(K2_DUAL_MATCH_MODE){
            auto [pL,pD]=findpred(p,CHAIN_DEPTH);'''
new='''        if(K2_DUAL_MATCH_MODE && !K2_FUSED_MATCH_MODE){
            auto [pL,pD]=findpred(p,CHAIN_DEPTH);'''
assert old in s
s=s.replace(old,new,1)

old='''            if(K2_DUAL_MATCH_MODE){
                auto [qL,qD]=findpred(p+1,localLazyDepth);'''
new='''            if(K2_DUAL_MATCH_MODE && !K2_FUSED_MATCH_MODE){
                auto [qL,qD]=findpred(p+1,localLazyDepth);'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP38_FUSED_DUAL.cpp").write_text(s)
print("EXP38_SOURCE_BYTES",len(s.encode()))
