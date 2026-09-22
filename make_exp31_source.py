from pathlib import Path
p=Path("KEPHIR_2_EXP27_LAZY_ADAPT.cpp")
s=p.read_text()

s=s.replace('#ifndef K2_LAZY_MODE\n#define K2_LAZY_MODE 0\n#endif',
'''#ifndef K2_LAZY_MODE
#define K2_LAZY_MODE 1
#endif
#ifndef K2_PSG_MODE
#define K2_PSG_MODE 0
#endif''',1)

needle='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
insert=r'''
static vector<double> k2_psg_literal_prefix_cost(const vector<uint8_t>& d,double LIT,int mode){
    vector<double> pref(d.size()+1,0.0);
    if(mode<=0){
        for(size_t i=0;i<d.size();++i) pref[i+1]=pref[i]+LIT;
        return pref;
    }
    K2Predictor kp;
    EncModel rm;
    double ema=LIT;
    for(size_t p=0;p<d.size();++p){
        uint8_t pr=kp.predict(d,p), x=d[p], r=(uint8_t)(x-pr);
        double pcost=kp.use_raw(p)?8.0:(K2LOG2(rm.total)-K2LOG2(rm.f[r]));
        double surprise=pcost-ema;
        double w=0.50;
        if(mode==1){
            // Asymmetric surprise gate: trust prediction more on expensive residuals.
            w = surprise>1.25 ? 0.72 : (surprise<-1.25 ? 0.35 : 0.50);
        } else if(mode==2){
            // Smooth confidence gate.
            double a=min(1.0,abs(surprise)/3.0);
            w = surprise>=0.0 ? 0.50+0.25*a : 0.50-0.20*a;
        } else {
            // Conservative three-zone gate.
            w = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
        }
        double c=(1.0-w)*LIT+w*pcost;
        c=max(1.5,min(10.0,c));
        pref[p+1]=pref[p]+c;
        ema=0.97*ema+0.03*pcost;
        rm.learn_lazy(r);
        if((p&PRED_SAMPLE_MASK)==0u) kp.observe_sampled(d,p);
    }
    return pref;
}
'''
assert needle in s
s=s.replace(needle,insert+"\n"+needle,1)

old='''    auto mcost=[&](int len,int dist)->double{
        return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
    };
    const int localLazyDepth=k2_lazy_depth(d,K2_LAZY_MODE);'''
new='''    auto mcost=[&](int len,int dist)->double{
        return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
    };
    const auto litPref=k2_psg_literal_prefix_cost(d,LIT,K2_PSG_MODE);
    auto lcost=[&](int p,int len)->double{
        int e=min(n,p+len);
        return litPref[(size_t)e]-litPref[(size_t)p];
    };
    const int localLazyDepth=k2_lazy_depth(d,K2_LAZY_MODE);'''
assert old in s
s=s.replace(old,new,1)

s=s.replace('bool take=bestL>=MINL && mcost(bestL,bestD)<LIT*bestL;',
            'bool take=bestL>=MINL && mcost(bestL,bestD)<lcost(p,bestL);',1)
s=s.replace('double gainNow=LIT*bestL-mcost(bestL,bestD);',
            'double gainNow=lcost(p,bestL)-mcost(bestL,bestD);',1)
s=s.replace('double gainNext=LIT*nL-mcost(nL,nD)-0.20;',
            'double gainNext=lcost(p+1,nL)-mcost(nL,nD)-0.20;',1)

Path("KEPHIR_2_EXP31_PSG.cpp").write_text(s)
print("EXP31_SOURCE_BYTES",len(s.encode()))
