#include "AuroraVideoCompute.h"
#include "AuroraVideoMotion.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes frame(std::uint32_t w,std::uint32_t h,std::uint32_t shift) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=0;x<w;++x) {
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((3u*x+5u*y+shift+((x/32u)%5u)*7u)&255u);
        }
    }
    for(std::size_t i=0;i<us;++i) {
        b[ys+i]=static_cast<Byte>((80u+i+shift)&255u);
        b[ys+us+i]=static_cast<Byte>((160u+3u*i+shift)&255u);
    }
    return b;
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        const auto prev=frame(w,h,0);
        const auto cur=frame(w,h,3);

        auto cpu=make_cpu_video_motion_compute();
        auto gpu=make_d3d12_video_motion_compute(true);

        const auto cm=cpu->motion_map_mc8r4(cur,prev,w,h);
        const auto gm=gpu->motion_map_mc8r4(cur,prev,w,h);

        if(cm.size()!=gm.size())
            throw std::runtime_error("motion map size mismatch");

        std::size_t mismatches=0;
        for(std::size_t i=0;i<cm.size();++i) {
            if(cm[i]!=gm[i]) {
                if(mismatches<16) {
                    std::cerr<<"MISMATCH block="<<i
                             <<" cpu="<<static_cast<unsigned>(cm[i])
                             <<" gpu="<<static_cast<unsigned>(gm[i])<<"\\n";
                }
                ++mismatches;
            }
        }

        if(mismatches!=0)
            throw std::runtime_error("CPU/GPU MC8R4 motion map mismatch count="+
                                     std::to_string(mismatches));

        const auto caps=gpu->capabilities();
        std::cout<<"AURORA_GPU_MC8R4_EQUIVALENCE_PASS blocks="<<cm.size()
                 <<" adapter="<<caps.adapter_name
                 <<" hardware="<<(caps.hardware_accelerated?1:0)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
