from pathlib import Path

p=Path("KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp")
s=p.read_text()

anchor='''#ifndef K2_SHARED_MATCH_CACHE_MODE
#define K2_SHARED_MATCH_CACHE_MODE 0
#endif'''
insert='''

#ifndef K2_DIST_LOG_CACHE_MODE
#define K2_DIST_LOG_CACHE_MODE 0
#endif
#ifndef K2_DIST_LOG_CACHE_BITS
#define K2_DIST_LOG_CACHE_BITS 12
#endif
'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

needle='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
cache='''    constexpr size_t k2DistLogCacheSize=(size_t)1u<<K2_DIST_LOG_CACHE_BITS;
    int k2DistLogKey[k2DistLogCacheSize]{};
    double k2DistLogVal[k2DistLogCacheSize]{};
    auto k2DistLog=[&](int dd)->double{
        if(!K2_DIST_LOG_CACHE_MODE)
            return log2((double)dd+1.0);
        const size_t i=((size_t)dd)&(k2DistLogCacheSize-1u);
        if(k2DistLogKey[i]==dd)
            return k2DistLogVal[i];
        const double v=log2((double)dd+1.0);
        k2DistLogKey[i]=dd;
        k2DistLogVal[i]=v;
        return v;
    };
    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
assert needle in s
s=s.replace(needle,cache,1)

old='''                double distPenalty=log2((double)dd+1.0);'''
new='''                double distPenalty=k2DistLog(dd);'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP42_DIST_LOG_CACHE.cpp").write_text(s)
print("EXP42_SOURCE_BYTES",len(s.encode()))
