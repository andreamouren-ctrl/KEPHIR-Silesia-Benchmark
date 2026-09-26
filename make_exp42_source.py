from pathlib import Path

p=Path("KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp")
s=p.read_text()

# EXP-42: exact distance-cost cache for the predictive match scorer.
# Parser decisions and K37M wire format must remain byte-identical.
# The only change is memoizing log2(distance+1) values in a thread-local cache.

anchor='''#ifndef K2_SHARED_MATCH_CACHE_MODE
#define K2_SHARED_MATCH_CACHE_MODE 0
#endif'''
insert='''

#ifndef K2_DIST_COST_CACHE_MODE
#define K2_DIST_COST_CACHE_MODE 0
#endif
'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

needle='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
cache=r'''    auto k2DistPenalty=[&](int dd)->double{
        if(K2_DIST_COST_CACHE_MODE && dd>0 && dd<=131072){
            static thread_local vector<double> cache(131073,0.0);
            double &v=cache[(size_t)dd];
            if(v==0.0) v=log2((double)dd+1.0);
            return v;
        }
        return log2((double)dd+1.0);
    };
    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
assert needle in s
s=s.replace(needle,cache,1)

old='''                double distPenalty=log2((double)dd+1.0);'''
new='''                double distPenalty=k2DistPenalty(dd);'''
count=s.count(old)
assert count>=1, count
s=s.replace(old,new)

Path("KEPHIR_2_EXP42_DISTANCE_COST_CACHE.cpp").write_text(s)
print("EXP42_SOURCE_BYTES",len(s.encode()))
print("EXP42_REPLACED_LOG2",count)
