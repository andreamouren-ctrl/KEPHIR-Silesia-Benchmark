#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraCodecInterfaces.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <unordered_map>
#include <vector>

using namespace aurora::media;

namespace {

double entropy_values(const std::vector<Byte>& vals){
    if(vals.empty()) return 0.0;
    std::unordered_map<int,std::size_t> c;
    for(auto v:vals) ++c[v];
    const double n=static_cast<double>(vals.size());
    double h=0.0;
    for(const auto& kv:c){
        const double p=kv.second/n;
        h-=p*std::log2(p);
    }
    return h;
}

double sample_entropy(ByteView b,std::size_t step=32){
    std::vector<Byte> s;
    s.reserve((b.size()+step-1)/step);
    for(std::size_t i=0;i<b.size();i+=step) s.push_back(b[i]);
    return entropy_values(s);
}

double residual_entropy(ByteView b,std::size_t lag,std::size_t step=32){
    if(b.size()<=lag) return 99.0;
    std::vector<Byte> s;
    s.reserve((b.size()-lag+step-1)/step);
    for(std::size_t i=lag;i<b.size();i+=step)
        s.push_back(static_cast<Byte>((static_cast<unsigned>(b[i])-static_cast<unsigned>(b[i-lag]))&255u));
    return entropy_values(s);
}

Bytes delta_lag(ByteView b,std::size_t lag){
    Bytes out(b.size());
    for(std::size_t i=0;i<b.size();++i)
        out[i]=i<lag?b[i]:static_cast<Byte>((static_cast<unsigned>(b[i])-static_cast<unsigned>(b[i-lag]))&255u);
    return out;
}

Bytes inv_delta(ByteView b,std::size_t lag){
    Bytes out(b.size());
    for(std::size_t i=0;i<b.size();++i)
        out[i]=i<lag?b[i]:static_cast<Byte>((static_cast<unsigned>(b[i])+static_cast<unsigned>(out[i-lag]))&255u);
    return out;
}

Bytes transpose(ByteView b,std::size_t w){
    const std::size_t rows=b.size()/w,main=rows*w;
    Bytes out; out.reserve(b.size());
    for(std::size_t c=0;c<w;++c)
        for(std::size_t i=c;i<main;i+=w) out.push_back(b[i]);
    out.insert(out.end(),b.begin()+static_cast<std::ptrdiff_t>(main),b.end());
    return out;
}

Bytes inv_transpose(ByteView b,std::size_t w,std::size_t rawlen){
    const std::size_t rows=rawlen/w,main=rows*w;
    Bytes out(rawlen); std::size_t k=0;
    for(std::size_t c=0;c<w;++c)
        for(std::size_t r=0;r<rows;++r) out[r*w+c]=b[k++];
    std::copy(b.begin()+static_cast<std::ptrdiff_t>(k),b.end(),out.begin()+static_cast<std::ptrdiff_t>(main));
    return out;
}

Bytes transform(ByteView b,int mode){
    if(mode==0) return Bytes(b.begin(),b.end());
    std::size_t lag=0;
    if(mode==4) lag=2;
    else if(mode==1) lag=4;
    else if(mode==5) lag=16;
    else if(mode==2) lag=1024;
    else throw std::runtime_error("bad EXP65 media mode");
    auto d=delta_lag(b,lag);
    return transpose(d,lag);
}

Bytes inverse(ByteView b,int mode,std::size_t rawlen){
    if(mode==0) return Bytes(b.begin(),b.end());
    std::size_t lag=0;
    if(mode==4) lag=2;
    else if(mode==1) lag=4;
    else if(mode==5) lag=16;
    else if(mode==2) lag=1024;
    else throw std::runtime_error("bad EXP65 media mode");
    auto t=inv_transpose(b,lag,rawlen);
    return inv_delta(t,lag);
}

int choose_mode(ByteView b){
    const double raw=sample_entropy(b);
    struct C{double h;int mode;};
    C best{raw,0};
    for(const auto& c:std::vector<C>{
        {residual_entropy(b,2),4},
        {residual_entropy(b,4),1},
        {residual_entropy(b,16),5},
        {residual_entropy(b,1024),2}}){
        if(c.h<best.h) best=c;
    }
    if(best.mode!=0 && raw-best.h<0.10) return 0;
    return best.mode;
}

void put32(Bytes& out,std::uint32_t v){
    out.push_back(static_cast<Byte>(v));
    out.push_back(static_cast<Byte>(v>>8));
    out.push_back(static_cast<Byte>(v>>16));
    out.push_back(static_cast<Byte>(v>>24));
}
std::uint32_t get32(ByteView b,std::size_t& p){
    if(p+4>b.size()) throw std::runtime_error("EXP65 media truncated");
    auto v=static_cast<std::uint32_t>(b[p])|
           (static_cast<std::uint32_t>(b[p+1])<<8)|
           (static_cast<std::uint32_t>(b[p+2])<<16)|
           (static_cast<std::uint32_t>(b[p+3])<<24);
    p+=4; return v;
}

struct State{
    AuroraKhepriExp37MemoryAdapter backend;
    Bytes scratch;
};

Bytes encode65(State& s,ByteView in){
    const int mode=choose_mode(in);
    auto base=s.backend.encode(in);
    int chosen=0;
    Bytes best=std::move(base);
    if(mode!=0){
        auto tr=transform(in,mode);
        auto candidate=s.backend.encode(tr);
        if(candidate.size()<best.size()){
            best=std::move(candidate);
            chosen=mode;
        }
    }
    Bytes out;
    out.reserve(9+best.size());
    out.insert(out.end(),{'K','6','5','M'});
    out.push_back(static_cast<Byte>(chosen));
    put32(out,static_cast<std::uint32_t>(in.size()));
    out.insert(out.end(),best.begin(),best.end());
    return out;
}

Bytes decode65(State& s,ByteView in){
    if(in.size()<9 || in[0]!='K'||in[1]!='6'||in[2]!='5'||in[3]!='M')
        throw std::runtime_error("EXP65 media bad header");
    const int mode=in[4];
    std::size_t p=5;
    const auto rawSize=get32(in,p);
    ByteView payload(in.data()+p,in.size()-p);
    auto tr=s.backend.decode(payload);
    auto raw=inverse(tr,mode,rawSize);
    if(raw.size()!=rawSize) throw std::runtime_error("EXP65 media size mismatch");
    return raw;
}

}

extern "C" {

struct AuroraPluginBuffer { unsigned char* data; std::size_t size; };

void* aurora_backend_create(){
    try{return new State();}catch(...){return nullptr;}
}
void aurora_backend_destroy(void* p){delete static_cast<State*>(p);}

AuroraPluginBuffer aurora_backend_encode(void* p,const unsigned char* data,std::size_t size){
    try{
        auto* s=static_cast<State*>(p);
        s->scratch=encode65(*s,ByteView(data,size));
        return {s->scratch.empty()?nullptr:s->scratch.data(),s->scratch.size()};
    }catch(...){return {nullptr,0};}
}

AuroraPluginBuffer aurora_backend_decode(void* p,const unsigned char* data,std::size_t size){
    try{
        auto* s=static_cast<State*>(p);
        s->scratch=decode65(*s,ByteView(data,size));
        return {s->scratch.empty()?nullptr:s->scratch.data(),s->scratch.size()};
    }catch(...){return {nullptr,0};}
}

void aurora_backend_free(unsigned char*){}

}
