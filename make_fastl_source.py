from pathlib import Path
p=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=p.read_text()

needle='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
helper=r'''
static pair<int,int> k2_fast_l_depths(const vector<uint8_t>& d){
    if(d.size()<4096) return {24,12};
    constexpr int S=4096;
    uint32_t keys[S]{};
    uint8_t used[S]{};
    int samples=0,repeats=0;
    for(size_t p=0;p+4<=d.size();p+=64){
        uint32_t v;
        memcpy(&v,d.data()+p,4);
        uint32_t h=(v*2654435761u)>>(32-12);
        if(used[h] && keys[h]==v) ++repeats;
        else {used[h]=1; keys[h]=v;}
        ++samples;
    }
    double r=samples?double(repeats)/double(samples):0.0;
    if(r<0.025) return {2,2};
    if(r<0.080) return {8,4};
    return {24,12};
}
'''
if needle not in s: raise SystemExit("ANCHOR")
s=s.replace(needle,helper+"\n"+needle,1)

old='    const int localLazyDepth=k2_lazy_depth(d,K2_LAZY_MODE);'
new='''    auto k2fl=k2_fast_l_depths(d);
    const int localChainDepth=k2fl.first;
    const int localLazyDepth=k2fl.second;'''
if old not in s: raise SystemExit("LAZY_ANCHOR")
s=s.replace(old,new,1)

if 'findbest(p,CHAIN_DEPTH)' not in s: raise SystemExit("MAIN_FIND")
s=s.replace('findbest(p,CHAIN_DEPTH)','findbest(p,localChainDepth)',1)

Path("KEPHIR_FAST_L.cpp").write_text(s)
print("FAST_L_READY")
