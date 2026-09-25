#include "AuroraCodecInterfaces.h"
#include <cstdint>
#include <iostream>
#include <vector>
#define main aurora_stats_cli_main
#include "../../KEPHIR_SPEED_D_STATS_SOURCE.cpp"
#undef main
using namespace aurora::media;

int main(){
    std::vector<std::uint8_t>d(512*1024);
    for(std::size_t i=0;i<d.size();++i){
        auto block=(i/4096)%8;
        d[i]=(std::uint8_t)((i*13 + block*7 + ((i>>5)&31))&255);
        if(i>8192 && (i%97)<48) d[i]=d[i-4096];
    }
    k2_stats_enabled=true;
    const double localDpen=k2_adaptive_dpen(d,1.20,K2_ADAPT_MODE);
    auto ts=parse(d,6.55,9.42,localDpen);
    k2_stats_enabled=false;
    auto enc=::encode(d,ts);
    auto dec=::decode(enc,d.size());
    if(dec!=d){std::cerr<<"FAIL roundtrip\n";return 1;}
    std::cout<<"FINDBEST_STATS_PASS"
             <<" nodes="<<k2_stats_nodes
             <<" h4="<<k2_stats_h4
             <<" prefilter="<<k2_stats_prefilter
             <<" extended="<<k2_stats_extended
             <<" stop_lim="<<k2_stats_stop_lim
             <<" stop128="<<k2_stats_stop128
             <<" stop64="<<k2_stats_stop64
             <<" stop32="<<k2_stats_stop32
             <<" packed_bytes="<<enc.size()
             <<" lossless=1\n";
    return 0;
}
