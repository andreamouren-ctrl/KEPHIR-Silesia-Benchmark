from pathlib import Path

p=Path("KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp")
s=p.read_text()

anchor='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
helper=r'''
static const vector<double>& k2_exp42_log2_table(){
    static const vector<double> t=[]{
        // Current KHEPRI media chunks are below 1 MiB. Keep a table through
        // 1 MiB and fall back to libm outside the profiled range.
        vector<double> v((1u<<20)+2u);
        v[0]=0.0;
        for(size_t i=1;i<v.size();++i)
            v[i]=log2((double)i);
        return v;
    }();
    return t;
}
static inline double k2_exp42_log2p1(unsigned v){
    const auto& t=k2_exp42_log2_table();
    const unsigned i=v+1u;
    return i<t.size()?t[i]:log2((double)i);
}
'''
if anchor not in s:
    raise SystemExit("PARSE_ANCHOR_NOT_FOUND")
s=s.replace(anchor,helper+"\n"+anchor,1)

# Exact parser-cost substitutions only. Mathematical expressions and parser
# decisions remain unchanged; only repeated libm evaluation is replaced by
# a table lookup generated from the same log2 implementation.
replacements=[
    ('log2(len+1.0)', 'k2_exp42_log2p1((unsigned)len)'),
    ('log2(dist+1.0)', 'k2_exp42_log2p1((unsigned)dist)'),
    ('log2((double)dd+1.0)', 'k2_exp42_log2p1((unsigned)dd)'),
]
counts=[]
for old,new in replacements:
    n=s.count(old)
    counts.append((old,n))
    s=s.replace(old,new)

if sum(n for _,n in counts)<2:
    raise SystemExit("EXP42_EXPECTED_LOG_COST_SITES_NOT_FOUND")

Path("KEPHIR_2_EXP42_LOG_COST_CACHE.cpp").write_text(s)
print("EXP42_SOURCE_BYTES",len(s.encode()))
print("EXP42_REPLACEMENTS",counts)
