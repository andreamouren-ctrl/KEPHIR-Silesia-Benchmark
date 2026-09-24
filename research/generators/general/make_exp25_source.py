from pathlib import Path
p=Path("KEPHIR_2_EXP23_BASE.cpp")
s=p.read_text()
marker='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
insert=r'''
#ifndef K2_ADAPT_MODE
#define K2_ADAPT_MODE 0
#endif
static double k2_clamp(double x,double lo,double hi){ return x<lo?lo:(x>hi?hi:x); }

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
    double n=(double)d.size(),H=0.0;
    for(uint32_t c:h) if(c){ double q=(double)c/n; H-=q*log2(q); }
    double text=(double)printable/n;
    double rep=d.size()>1?(double)eq1/(double)(d.size()-1):0.0;

    // EXP-24B control
    if(mode==2){
        if(text>=0.80) return 1.05;
        if(text<=0.35) return 0.98;
        return 1.18;
    }

    // EXP-25A: continuous text-only
    if(mode==4){
        return k2_clamp(1.30 - 0.30*text, 0.94, 1.26);
    }

    // EXP-25B: continuous text + entropy
    if(mode==5){
        double dpen = 1.24 - 0.22*text - 0.045*(H-5.5);
        return k2_clamp(dpen,0.90,1.27);
    }

    // EXP-25C: text + entropy + local repetition
    double dpen = 1.22 - 0.18*text - 0.050*(H-5.5) + 0.32*rep;
    return k2_clamp(dpen,0.88,1.28);
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
Path("KEPHIR_2_EXP25_CONTINUOUS.cpp").write_text(s)
print("EXP25_SOURCE_BYTES",len(s.encode()))
