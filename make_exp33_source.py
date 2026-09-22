from pathlib import Path
p=Path("KEPHIR_2_EXP31_PSG.cpp")
s=p.read_text()

s=s.replace('#ifndef K2_PSG_MODE\n#define K2_PSG_MODE 0\n#endif',
'''#ifndef K2_PSG_MODE
#define K2_PSG_MODE 3
#endif
#ifndef K2_DIST_TOPO_MODE
#define K2_DIST_TOPO_MODE 0
#endif''',1)

old='''    auto mcost=[&](int len,int dist)->double{
        return MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
    };'''
new='''    int prevTopoDist=0, prevTopoDist2=0;
    auto mcost=[&](int len,int dist)->double{
        double c=MC+(len<=7?1.0:log2(len+1.0))+maxDistPenalty*log2(dist+1.0);
        if(K2_DIST_TOPO_MODE==1){
            // Recent-distance topology: reward exact/near reuse and simple harmonics.
            if(prevTopoDist>0){
                if(dist==prevTopoDist) c-=1.05;
                else {
                    int tol=max(2,prevTopoDist>>5);
                    if(abs(dist-prevTopoDist)<=tol) c-=0.38;
                    if(abs(dist-2*prevTopoDist)<=tol*2 || abs(2*dist-prevTopoDist)<=tol*2) c-=0.20;
                }
            }
        }else if(K2_DIST_TOPO_MODE==2){
            // Native KEPHIR lattice topology: 16-wide lines and 256-wide planes.
            if(dist==15 || dist==16 || dist==17) c-=0.40;
            if(dist==255 || dist==256 || dist==257) c-=0.70;
            else if((dist&255)==0) c-=0.46;
            else if((dist&15)==0) c-=0.22;
        }else if(K2_DIST_TOPO_MODE==3){
            // Hybrid recurrence + lattice, deliberately conservative.
            if(prevTopoDist>0){
                if(dist==prevTopoDist) c-=0.70;
                else if(abs(dist-prevTopoDist)<=max(2,prevTopoDist>>6)) c-=0.24;
            }
            if(prevTopoDist2>0 && dist==prevTopoDist2) c-=0.18;
            if(dist==255 || dist==256 || dist==257) c-=0.42;
            else if((dist&255)==0) c-=0.28;
            else if((dist&15)==0) c-=0.12;
        }
        return c;
    };'''
assert old in s
s=s.replace(old,new,1)

old2='''        if(take){
            out.push_back({bestL,bestD});
            int e=min(n,p+bestL);'''
new2='''        if(take){
            out.push_back({bestL,bestD});
            prevTopoDist2=prevTopoDist; prevTopoDist=bestD;
            int e=min(n,p+bestL);'''
assert old2 in s
s=s.replace(old2,new2,1)

Path("KEPHIR_2_EXP33_DISTANCE_TOPOLOGY.cpp").write_text(s)
print("EXP33_SOURCE_BYTES",len(s.encode()))
