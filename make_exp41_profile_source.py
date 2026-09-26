from pathlib import Path
# EXP-41 profile trigger: instrumentation-only, no bitstream change\nfrom pathlib import Path

p=Path("KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp")
s=p.read_text()

anchor='''#ifndef K2_SHARED_MATCH_CACHE_MODE
#define K2_SHARED_MATCH_CACHE_MODE 0
#endif'''
profile='''

struct K2Exp41Profile {
    unsigned long long findbest_calls=0;
    unsigned long long findpred_calls=0;
    unsigned long long findbest_nodes=0;
    unsigned long long findpred_nodes=0;
    unsigned long long findbest_early_stops=0;
    unsigned long long shared_cache_hits=0;
    unsigned long long shared_cache_misses=0;
    unsigned long long predictive_match_computes=0;
    unsigned long long predictive_scored_candidates=0;
};
static K2Exp41Profile k2_exp41_profile;
static void k2_exp41_reset_profile(){ k2_exp41_profile=K2Exp41Profile{}; }
'''
assert anchor in s
s=s.replace(anchor,anchor+profile,1)

old='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{
        int bestL=0,bestD=0;'''
new='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{
        ++k2_exp41_profile.findbest_calls;
        int bestL=0,bestD=0;'''
assert old in s
s=s.replace(old,new,1)

# Instrument only the first chain loop: findbest.
old='''        while(q!=NIL && depth<maxDepth){
            if(K2_SHARED_MATCH_CACHE_MODE && depth<256){'''
new='''        while(q!=NIL && depth<maxDepth){
            ++k2_exp41_profile.findbest_nodes;
            if(K2_SHARED_MATCH_CACHE_MODE && depth<256){'''
assert old in s
s=s.replace(old,new,1)

old='''                if(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32)) break;'''
new='''                if(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32)){
                    ++k2_exp41_profile.findbest_early_stops;
                    break;
                }'''
assert old in s
s=s.replace(old,new,1)

old='''    auto findpred=[&](int p,int maxDepth)->pair<int,int>{
        int bestL=0,bestD=0; double bestScore=-1e300;'''
new='''    auto findpred=[&](int p,int maxDepth)->pair<int,int>{
        ++k2_exp41_profile.findpred_calls;
        int bestL=0,bestD=0; double bestScore=-1e300;'''
assert old in s
s=s.replace(old,new,1)

# This exact loop occurs in findpred after the findbest loop was already modified.
needle='''        while(q!=NIL && depth<maxDepth){
            int dd=p-(int)q;
            int l=0;
            const bool cached='''
repl='''        while(q!=NIL && depth<maxDepth){
            ++k2_exp41_profile.findpred_nodes;
            int dd=p-(int)q;
            int l=0;
            const bool cached='''
assert needle in s
s=s.replace(needle,repl,1)

old='''            if(cached){
                l=k2SharedL[depth];
            }else if(dd>0 && dd<=W && q+3<n && h4(q)==hp){
                l=4;'''
new='''            if(cached){
                ++k2_exp41_profile.shared_cache_hits;
                l=k2SharedL[depth];
            }else if(dd>0 && dd<=W && q+3<n && h4(q)==hp){
                ++k2_exp41_profile.shared_cache_misses;
                ++k2_exp41_profile.predictive_match_computes;
                l=4;'''
assert old in s
s=s.replace(old,new,1)

old='''            if(l>=MINL){
                double lit=dualLcost(p,l);'''
new='''            if(l>=MINL){
                ++k2_exp41_profile.predictive_scored_candidates;
                double lit=dualLcost(p,l);'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP41_PROFILE.cpp").write_text(s)
print("EXP41_SOURCE_BYTES",len(s.encode()))
