from pathlib import Path
p=Path("KEPHIR_2_EXP27_LAZY_ADAPT.cpp")
s=p.read_text()

s=s.replace('#ifndef K2_LAZY_MODE\n#define K2_LAZY_MODE 0\n#endif',
'''#ifndef K2_LAZY_MODE
#define K2_LAZY_MODE 1
#endif
#ifndef K2_SPOF_MODE
#define K2_SPOF_MODE 1
#endif''',1)

needle='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
insert=r'''
static vector<double> k2_spof_literal_prefix_cost(const vector<uint8_t>& d,double LIT,int mode){
    vector<double> pref(d.size()+1,0.0);
    K2Predictor kp;
    EncModel rm;
    int stride = mode==1 ? 1 : (mode==2 ? 2 : (mode==3 ? 4 : 8));
    double lastCost=LIT;
    for(size_t p=0;p<d.size();++p){
        bool sample=(p%(size_t)stride)==0u;
        if(sample){
            uint8_t pr=kp.predict(d,p), x=d[p], r=(uint8_t)(x-pr);
            double pcost=kp.use_raw(p)?8.0:(K2LOG2(rm.total)-K2LOG2(rm.f[r]));
            lastCost=max(1.5,min(10.0,0.50*LIT+0.50*pcost));
            rm.learn_lazy(r);
            if((p&PRED_SAMPLE_MASK)==0u) kp.observe_sampled(d,p);
        } else {
            // Slow local drift toward the neutral literal cost between predictive samples.
            lastCost=0.92*lastCost+0.08*LIT;
        }
        pref[p+1]=pref[p]+lastCost;
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
    const auto litPref=k2_spof_literal_prefix_cost(d,LIT,K2_SPOF_MODE);
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

Path("KEPHIR_2_EXP32_SPOF.cpp").write_text(s)
print("EXP32_SOURCE_BYTES",len(s.encode()))
