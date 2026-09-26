from pathlib import Path

p=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
s=p.read_text()

# EXP-40: exact shared match-length cache between findbest and findpred.
# The parser decisions are intentionally unchanged. findbest keeps its historical
# early-stop behavior; findpred keeps its historical traversal depth and scoring.
# Only already-computed match lengths from the overlapping chain prefix are reused.

anchor='#ifndef K2_DUAL_MATCH_MODE\n#define K2_DUAL_MATCH_MODE 0\n#endif'
insert='''\n#ifndef K2_SHARED_MATCH_CACHE_MODE\n#define K2_SHARED_MATCH_CACHE_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

findbest_start=s.index('    auto findbest=[&](int p,int maxDepth)->pair<int,int>{')
findpred_start=s.index('    auto findpred=[&](int p,int maxDepth)->pair<int,int>{',findbest_start)
after_pred=s.index('    int prevTopoDist=0, prevTopoDist2=0;',findpred_start)

prefix=s[:findbest_start]
findbest=s[findbest_start:findpred_start]
findpred=s[findpred_start:after_pred]
suffix=s[after_pred:]

cache_decl='''    // Shared scratch for the immediately following predictive search.
    // 256 exceeds all current CHAIN/LAZY research depths. If a future depth
    // exceeds this cap, the tail simply falls back to the historical compute path.
    uint32_t k2SharedQ[256]{};
    int k2SharedL[256]{};
    int k2SharedP=-1;
    int k2SharedN=0;
'''

findbest=cache_decl+findbest

old='''        int bestL=0,bestD=0;
        if(p+MINL>n) return {0,0};'''
new='''        int bestL=0,bestD=0;
        if(K2_SHARED_MATCH_CACHE_MODE){
            k2SharedP=p;
            k2SharedN=0;
        }
        if(p+MINL>n) return {0,0};'''
assert old in findbest
findbest=findbest.replace(old,new,1)

old='''        while(q!=NIL && depth<maxDepth){
            int dd=p-(int)q;
            if(dd>0 && dd<=W && q+3<n && h4(q)==hp){'''
new='''        while(q!=NIL && depth<maxDepth){
            if(K2_SHARED_MATCH_CACHE_MODE && depth<256){
                k2SharedQ[depth]=q;
                k2SharedL[depth]=0;
                k2SharedN=depth+1;
            }
            int dd=p-(int)q;
            if(dd>0 && dd<=W && q+3<n && h4(q)==hp){'''
assert old in findbest
findbest=findbest.replace(old,new,1)

old='''                while(l<lim && d[q+l]==d[p+l]) ++l;
                if(l>bestL){bestL=l;bestD=dd;}'''
new='''                while(l<lim && d[q+l]==d[p+l]) ++l;
                if(K2_SHARED_MATCH_CACHE_MODE && depth<256)
                    k2SharedL[depth]=l;
                if(l>bestL){bestL=l;bestD=dd;}'''
assert old in findbest
findbest=findbest.replace(old,new,1)

old_body=r'''        while(q!=NIL && depth<maxDepth){
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
        }'''

new_body=r'''        while(q!=NIL && depth<maxDepth){
            int dd=p-(int)q;
            int l=0;
            const bool cached=
                K2_SHARED_MATCH_CACHE_MODE &&
                p==k2SharedP &&
                depth<k2SharedN &&
                depth<256 &&
                k2SharedQ[depth]==q;
            if(cached){
                l=k2SharedL[depth];
            }else if(dd>0 && dd<=W && q+3<n && h4(q)==hp){
                l=4;
                while(l+8<=lim){
                    uint64_t a,b; memcpy(&a,d.data()+q+l,8); memcpy(&b,d.data()+p+l,8);
                    uint64_t x=a^b;
                    if(x){ l += (int)(__builtin_ctzll(x)>>3); break; }
                    l+=8;
                }
                while(l<lim && d[q+l]==d[p+l]) ++l;
            }
            if(l>=MINL){
                double lit=dualLcost(p,l);
                double distPenalty=log2((double)dd+1.0);
                double score=lit;
                if(K2_DUAL_MATCH_MODE==1) score-=1.35*distPenalty;
                else if(K2_DUAL_MATCH_MODE==2) score-=0.95*distPenalty;
                else score-=0.65*distPenalty;
                // Preserve the historical predictive scoring exactly.
                if(l<8) score-=2.0;
                if(score>bestScore){bestScore=score;bestL=l;bestD=dd;}
            }
            q=prev[q]; ++depth;
        }'''

assert old_body in findpred
findpred=findpred.replace(old_body,new_body,1)

s=prefix+findbest+findpred+suffix

Path("KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp").write_text(s)
print("EXP40_SOURCE_BYTES",len(s.encode()))
