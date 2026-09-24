from pathlib import Path
p=Path("KEPHIR_FAST_V.cpp")
s=p.read_text()

anchor='struct K2CompressChunk { vector<uint8_t> raw, comp; exception_ptr error=nullptr; };'
helper=r'''
static inline bool k2_fast_pre_raw_gate(const vector<uint8_t>& d){
    if(d.size()<8192) return false;
    constexpr int S=4096;
    uint32_t keys[S]{};
    uint8_t used[S]{};
    int samples=0,repeats=0;
    size_t step=max<size_t>(64,d.size()/4096);
    for(size_t p=0;p+4<=d.size();p+=step){
        uint32_t v;
        memcpy(&v,d.data()+p,4);
        uint32_t h=(v*2654435761u)>>(32-12);
        if(used[h] && keys[h]==v) ++repeats;
        else {used[h]=1; keys[h]=v;}
        ++samples;
    }
    return samples>=256 && repeats*1000 <= samples;
}
'''
if anchor not in s: raise SystemExit("CHUNK_ANCHOR_NOT_FOUND")
s=s.replace(anchor,helper+"\n"+anchor,1)

old='''            double localDPEN=k2_adaptive_dpen(ch.raw,DPEN,K2_ADAPT_MODE); auto ts=parse(ch.raw,LIT,MC,localDPEN); size_t literals=0; for(auto &t:ts) if(!t.dist)++literals;
            if(literals>ch.raw.size()*9/10){ ch.comp=ch.raw; ch.comp.push_back(0); } else { ch.comp=encode(ch.raw,ts);
#ifndef NO_INTERNAL_VERIFY
                auto rr=decode(ch.comp,ch.raw.size()); if(rr!=ch.raw) throw runtime_error("Parallel BYTE-PERFECT verification failed");
#endif
            }'''
new='''            if(k2_fast_pre_raw_gate(ch.raw)){
                ch.comp=ch.raw; ch.comp.push_back(0);
            } else {
                double localDPEN=k2_adaptive_dpen(ch.raw,DPEN,K2_ADAPT_MODE); auto ts=parse(ch.raw,LIT,MC,localDPEN); size_t literals=0; for(auto &t:ts) if(!t.dist)++literals;
                if(literals>ch.raw.size()*9/10){ ch.comp=ch.raw; ch.comp.push_back(0); } else { ch.comp=encode(ch.raw,ts);
#ifndef NO_INTERNAL_VERIFY
                    auto rr=decode(ch.comp,ch.raw.size()); if(rr!=ch.raw) throw runtime_error("Parallel BYTE-PERFECT verification failed");
#endif
                }
            }'''
if old not in s: raise SystemExit("PARALLEL_BLOCK_NOT_FOUND")
s=s.replace(old,new,1)

Path("KEPHIR_FAST_X.cpp").write_text(s)
print("FAST_X_PRE_RAW_GATE_READY",len(s))
