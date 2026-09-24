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
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((3u*x+5u*y+shift+((x/32u)%5u)*7u)&255u);
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

        const auto cpuEncoded=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
        auto gpu=make_d3d12_video_motion_compute(true);
        const auto residual=gpu->residual_yuv420_mc8r4(
            cur,prev,cpuEncoded.motion_map,w,h);

        if(residual.size()!=cpuEncoded.residual_yuv420.size())
            throw std::runtime_error("residual size mismatch");

        std::size_t mismatches=0;
        for(std::size_t i=0;i<residual.size();++i) {
            if(residual[i]!=cpuEncoded.residual_yuv420[i]) {
                if(mismatches<8)
                    std::cerr<<"MISMATCH byte="<<i
                             <<" cpu="<<static_cast<unsigned>(cpuEncoded.residual_yuv420[i])
                             <<" gpu="<<static_cast<unsigned>(residual[i])<<"\n";
                ++mismatches;
            }
        }
        if(mismatches)
            throw std::runtime_error("CPU/GPU residual mismatch count="+std::to_string(mismatches));

        std::cout<<"AURORA_GPU_RESIDUAL_EQUIVALENCE_PASS bytes="<<residual.size()<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
