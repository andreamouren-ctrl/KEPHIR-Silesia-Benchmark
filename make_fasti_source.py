from pathlib import Path
p=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=p.read_text()

anchor='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
helper=r'''
static const vector<double>& k2_fast_log2_table(){
    static const vector<double> t=[]{
        // KHEPRI chunks are <= 512 KiB in this profile; keep margin to 1 MiB.
        vector<double> v((1u<<20)+2u);
        v[0]=0.0;
        for(size_t i=1;i<v.size();++i) v[i]=log2((double)i);
        return v;
    }();
    return t;
}
static inline double k2_fast_log2p1(unsigned v){
    const auto& t=k2_fast_log2_table();
    unsigned i=v+1u;
    return i<t.size()?t[i]:log2((double)i);
}
'''
if anchor not in s: raise SystemExit("PARSE_ANCHOR_NOT_FOUND")
s=s.replace(anchor,helper+"\n"+anchor,1)

# Replace parser cost log2 calls while preserving exact mathematical expression.
s=s.replace('log2(len+1.0)', 'k2_fast_log2p1((unsigned)len)')
s=s.replace('log2(dist+1.0)', 'k2_fast_log2p1((unsigned)dist)')

Path("KEPHIR_FAST_I.cpp").write_text(s)
print("FAST_I_READY",len(s))
