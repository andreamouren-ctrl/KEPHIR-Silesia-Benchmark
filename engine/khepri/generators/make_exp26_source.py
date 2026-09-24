from pathlib import Path
p=Path("KEPHIR_2_EXP23_BASE.cpp")
s=p.read_text()
marker='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
insert=r'''
#ifndef K2_ADAPT_MODE
#define K2_ADAPT_MODE 2
#endif
static double k2_adaptive_dpen(const vector<uint8_t>& d,double base,int mode){
    if(mode<=0 || d.empty()) return base;
    size_t printable=0;
    for(uint8_t c:d) if((c>=32&&c<=126)||c==9||c==10||c==13) ++printable;
    double text=(double)printable/(double)d.size();

    // EXP-24B control
    if(mode==2){
        if(text>=0.80) return 1.05;
        if(text<=0.35) return 0.98;
        return 1.18;
    }
    // EXP-26A: wider text class, stronger binary preference
    if(mode==7){
        if(text>=0.78) return 1.03;
        if(text<=0.30) return 0.94;
        return 1.17;
    }
    // EXP-26B: broader binary class, slightly lower middle penalty
    if(mode==8){
        if(text>=0.82) return 1.04;
        if(text<=0.40) return 0.96;
        return 1.16;
    }
    // EXP-26C: aggressive three-band tuning
    if(text>=0.75) return 1.02;
    if(text<=0.35) return 0.95;
    return 1.15;
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
Path("KEPHIR_2_EXP26_BANDS.cpp").write_text(s)
print("EXP26_SOURCE_BYTES",len(s.encode()))
