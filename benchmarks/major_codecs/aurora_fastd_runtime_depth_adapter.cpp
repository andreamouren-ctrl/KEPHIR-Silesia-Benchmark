#include "AuroraCodecInterfaces.h"
#include "AuroraMediaError.h"
#include <cstdint>
#include <limits>
#include <vector>

#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#define main aurora_fastd_runtime_cli_main
#include "../../KEPHIR_SPEED_D_RUNTIME_SOURCE.cpp"
#undef main
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

using namespace aurora::media;

namespace {
constexpr double kLit=6.55,kMc=9.42,kDpen=1.20;
constexpr std::size_t kHeader=16;
void put32(Bytes&o,std::uint32_t v){o.push_back((Byte)v);o.push_back((Byte)(v>>8));o.push_back((Byte)(v>>16));o.push_back((Byte)(v>>24));}
std::uint32_t get32(ByteView in,std::size_t&p){auto v=(std::uint32_t)in[p]|((std::uint32_t)in[p+1]<<8)|((std::uint32_t)in[p+2]<<16)|((std::uint32_t)in[p+3]<<24);p+=4;return v;}
}

extern "C" {

void aurora_fastd_runtime_set_depths(int chain,int lazy){
    k2_runtime_chain_depth=chain;
    k2_runtime_lazy_depth=lazy;
}

Bytes aurora_fastd_runtime_encode(ByteView input){
    std::vector<std::uint8_t>d(input.begin(),input.end());
    std::vector<std::uint8_t> payload;
    std::uint8_t mode=0;
    if(!d.empty()){
        const double localDpen=k2_adaptive_dpen(d,kDpen,K2_ADAPT_MODE);
        const auto ts=parse(d,kLit,kMc,localDpen);
        auto enc=::encode(d,ts);
        if(enc.size()<d.size()){payload=std::move(enc);mode=1;}else payload=d;
    }
    Bytes out;out.reserve(kHeader+payload.size());
    out.insert(out.end(),{'K','R','T','D'});out.push_back(1);out.push_back(mode);out.push_back(0);out.push_back(0);
    put32(out,(std::uint32_t)d.size());put32(out,(std::uint32_t)payload.size());
    out.insert(out.end(),payload.begin(),payload.end());return out;
}

Bytes aurora_fastd_runtime_decode(ByteView input){
    if(input.size()<kHeader)throw std::runtime_error("short");
    std::size_t p=8;auto raw=get32(input,p);auto psz=get32(input,p);
    if(p+psz!=input.size())throw std::runtime_error("size");
    std::vector<std::uint8_t> pay(input.begin()+(std::ptrdiff_t)p,input.end());
    if(input[5]==0)return Bytes(pay.begin(),pay.end());
    auto dec=::decode(pay,raw);
    return Bytes(dec.begin(),dec.end());
}

}
