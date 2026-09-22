from pathlib import Path
p=Path("KEPHIR_2_EXP27_LAZY_ADAPT.cpp")
s=p.read_text()
# Add compile-time mode near lazy mode.
s=s.replace('#ifndef K2_LAZY_MODE\n#define K2_LAZY_MODE 0\n#endif',
'''#ifndef K2_LAZY_MODE
#define K2_LAZY_MODE 1
#endif
#ifndef K2_COMPETE_MODE
#define K2_COMPETE_MODE 0
#endif''',1)

helper=r'''
static vector<Tok> k2_all_literal_tokens(size_t n){
    vector<Tok> ts; ts.resize(n);
    for(size_t i=0;i<n;++i){ ts[i].len=1; ts[i].dist=0; }
    return ts;
}
static vector<uint8_t> k2_competitive_encode(const vector<uint8_t>& d,const vector<Tok>& lzts,size_t literalCount){
    vector<uint8_t> best;
    if(literalCount>d.size()*9/10){
        best=d; best.push_back(0);
    }else{
        best=encode(d,lzts);
    }
#if K2_COMPETE_MODE>=1
    bool tryPred=true;
    #if K2_COMPETE_MODE==2
        tryPred = literalCount*100 >= d.size()*55;
    #elif K2_COMPETE_MODE==3
        tryPred = literalCount*100 >= d.size()*35;
    #endif
    if(tryPred){
        auto pts=k2_all_literal_tokens(d.size());
        auto pc=encode(d,pts);
        if(pc.size()<best.size()) best.swap(pc);
    }
#endif
    if(best.size()>=d.size()+1){
        best=d; best.push_back(0);
    }
    return best;
}
'''
needle='static int compress_path(const string& input,const string& archive,double LIT,double MC,double DPEN,bool verbose){'
assert needle in s
s=s.replace(needle,helper+"\n"+needle,1)

old='''            size_t literals=0; for(const auto &t:ts) if(!t.dist) ++literals;
            if(literals > d.size()*9/10){ c=d; c.push_back(0); }
            else { c=encode(d,ts);
#ifndef NO_INTERNAL_VERIFY
 auto r=decode(c,d.size()); if(r!=d) throw runtime_error("Internal BYTE-PERFECT verification failed");
#endif
 }'''
new='''            size_t literals=0; for(const auto &t:ts) if(!t.dist) ++literals;
            c=k2_competitive_encode(d,ts,literals);
#ifndef NO_INTERNAL_VERIFY
 if(!(c.size()==d.size()+1 && c.back()==0)){ auto r=decode(c,d.size()); if(r!=d) throw runtime_error("Internal BYTE-PERFECT verification failed"); }
#endif'''
assert old in s
s=s.replace(old,new,1)

old2='''            double localDPEN=k2_adaptive_dpen(ch.raw,DPEN,K2_ADAPT_MODE); auto ts=parse(ch.raw,LIT,MC,localDPEN); size_t literals=0; for(auto &t:ts) if(!t.dist)++literals;
            if(literals>ch.raw.size()*9/10){ ch.comp=ch.raw; ch.comp.push_back(0); } else { ch.comp=encode(ch.raw,ts);
#ifndef NO_INTERNAL_VERIFY
                auto rr=decode(ch.comp,ch.raw.size()); if(rr!=ch.raw) throw runtime_error("Parallel BYTE-PERFECT verification failed");
#endif
            }'''
new2='''            double localDPEN=k2_adaptive_dpen(ch.raw,DPEN,K2_ADAPT_MODE); auto ts=parse(ch.raw,LIT,MC,localDPEN); size_t literals=0; for(auto &t:ts) if(!t.dist)++literals;
            ch.comp=k2_competitive_encode(ch.raw,ts,literals);
#ifndef NO_INTERNAL_VERIFY
            if(!(ch.comp.size()==ch.raw.size()+1 && ch.comp.back()==0)){ auto rr=decode(ch.comp,ch.raw.size()); if(rr!=ch.raw) throw runtime_error("Parallel BYTE-PERFECT verification failed"); }
#endif'''
assert old2 in s
s=s.replace(old2,new2,1)

Path("KEPHIR_2_EXP29_COMPETE.cpp").write_text(s)
print("EXP29_SOURCE_BYTES",len(s.encode()))
