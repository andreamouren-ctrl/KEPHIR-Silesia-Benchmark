from pathlib import Path
p=Path("KEPHIR_2_EXP26_BANDS.cpp")
s=p.read_text()
needle='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
inject=r'''
#ifndef K2_LAZY_MODE
#define K2_LAZY_MODE 0
#endif
static int k2_lazy_depth(const vector<uint8_t>& d,int mode){
    if(mode<=0 || d.empty()) return LAZY_DEPTH;
    size_t printable=0;
    for(uint8_t c:d) if((c>=32&&c<=126)||c==9||c==10||c==13) ++printable;
    double text=(double)printable/(double)d.size();
    if(mode==1) return text>=0.75 ? 28 : 19;
    if(mode==2) return text<=0.35 ? 28 : 19;
    if(text>=0.75) return 24;
    if(text<=0.35) return 30;
    return 22;
}
'''
assert needle in s
s=s.replace(needle,inject+"\n"+needle,1)
needle2='    for(int p=0;p<n;){'
replace2='    const int localLazyDepth=k2_lazy_depth(d,K2_LAZY_MODE);\n    for(int p=0;p<n;){'
assert needle2 in s
s=s.replace(needle2,replace2,1)
old='auto [nL,nD]=findbest(p+1,LAZY_DEPTH);'
new='auto [nL,nD]=findbest(p+1,localLazyDepth);'
assert old in s
s=s.replace(old,new,1)
Path("KEPHIR_2_EXP27_LAZY_ADAPT.cpp").write_text(s)
print("EXP27_SOURCE_BYTES",len(s.encode()))
