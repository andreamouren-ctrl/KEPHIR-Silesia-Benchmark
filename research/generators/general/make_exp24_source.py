from pathlib import Path
p=Path("KEPHIR_2_EXP23_BASE.cpp")
s=p.read_text()
marker='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
insert=r'''
#ifndef K2_ADAPT_MODE
#define K2_ADAPT_MODE 0
#endif
static double k2_adaptive_dpen(const vector<uint8_t>& d,double base,int mode){
    if(mode<=0 || d.empty()) return base;
    array<uint32_t,256> h{};
    size_t printable=0,eq1=0;
    for(size_t i=0;i<d.size();++i){
        ++h[d[i]];
        uint8_t c=d[i];
        if((c>=32&&c<=126)||c==9||c==10||c==13) ++printable;
        if(i && d[i]==d[i-1]) ++eq1;
    }
    double H=0.0,n=(double)d.size();
    for(uint32_t c:h) if(c){ double q=(double)c/n; H-=q*log2(q); }
    double text=(double)printable/n;
    double rep=d.size()>1?(double)eq1/(double)(d.size()-1):0.0;
    if(mode==1){
        if(H>=7.2) return 0.95;
        if(H>=6.2) return 1.05;
        if(H<=4.2) return 1.32;
        return 1.18;
    }
    if(mode==2){
        if(text>=0.80) return 1.05;
        if(text<=0.35) return 0.98;
        return 1.18;
    }
    if(H>=7.0 && rep<0.03) return 0.92;
    if(H<=4.5 || rep>0.16) return 1.30;
    if(text>=0.75) return 1.05;
    return 1.12;
}
'''
assert marker in s
s=s.replace(marker,insert+"\n"+marker,1)
old='d.resize((size_t)got); auto ts=parse(d,LIT,MC,DPEN); vector<uint8_t> c;'
new='d.resize((size_t)got); double localDPEN=k2_adaptive_dpen(d,DPEN,K2_ADAPT_MODE); auto ts=parse(d,LIT,MC,localDPEN); vector<uint8_t> c;'
assert old in s
s=s.replace(old,new,1)
old2='auto ts=parse(ch.raw,LIT,MC,DPEN); size_t literals=0;'
new2='double localDPEN=k2_adaptive_dpen(ch.raw,DPEN,K2_ADAPT_MODE); auto ts=parse(ch.raw,LIT,MC,localDPEN); size_t literals=0;'
assert old2 in s
s=s.replace(old2,new2,1)
Path("KEPHIR_2_EXP24_ADAPTIVE.cpp").write_text(s)
print("EXP24_SOURCE_BYTES",len(s.encode()))
