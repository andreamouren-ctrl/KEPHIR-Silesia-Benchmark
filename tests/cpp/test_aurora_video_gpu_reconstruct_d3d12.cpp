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
        const auto reconstructed=gpu->reconstruct_yuv420_mc8r4(
            prev,cpuEncoded.residual_yuv420,cpuEncoded.motion_map,w,h);

        const auto cpuReconstructed=AuroraVideoMotion::decode_mc8r4(
            cpuEncoded.motion_map,cpuEncoded.residual_yuv420,prev,w,h);

        if(reconstructed.size()!=cpuReconstructed.size())
            throw std::runtime_error("reconstruction size mismatch");

        std::size_t mismatches=0;
        for(std::size_t i=0;i<reconstructed.size();++i) {
            if(reconstructed[i]!=cpuReconstructed[i]) {
                if(mismatches<8)
                    std::cerr<<"MISMATCH byte="<<i
                             <<" cpu="<<static_cast<unsigned>(cpuReconstructed[i])
                             <<" gpu="<<static_cast<unsigned>(reconstructed[i])<<"\n";
                ++mismatches;
            }
        }
        if(mismatches)
            throw std::runtime_error("CPU/GPU reconstruction mismatch count="+std::to_string(mismatches));

        if(reconstructed!=cur)
            throw std::runtime_error("GPU reconstruction does not match source frame");

        std::cout<<"AURORA_GPU_RECONSTRUCT_EQUIVALENCE_PASS bytes="<<reconstructed.size()<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
