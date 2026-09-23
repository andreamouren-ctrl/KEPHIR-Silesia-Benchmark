#include "AuroraVideoMotion.h"
#include "AuroraVideoResidual.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes frame(std::uint32_t w,std::uint32_t h,int shift) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);

    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((x+y+shift)&255);

    for(std::size_t i=0;i<us;++i) {
        b[ys+i]=static_cast<Byte>((64+i+shift)&255);
        b[ys+us+i]=static_cast<Byte>((192+i+shift)&255);
    }
    return b;
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        auto prev=frame(w,h,0);
        auto cur=frame(w,h,1);

        auto enc=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
        auto dec=AuroraVideoMotion::decode_mc8r4(enc.motion_map,enc.residual_yuv420,prev,w,h);

        if(dec!=cur) throw std::runtime_error("MC8R4 roundtrip");
        if(enc.motion_map.size()!=(w/8)*(h/8))
            throw std::runtime_error("motion map size");

        const auto mode=AuroraVideoResidual::choose_mode(enc.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(enc.residual_yuv420,mode);
        auto un=AuroraVideoResidual::unmap(mapped,mode);
        if(un!=enc.residual_yuv420)
            throw std::runtime_error("motion residual map roundtrip");

        std::cout<<"VIDEO_MOTION_CPP_PASS blocks="<<enc.motion_map.size()
                 <<" mean_residual="<<AuroraVideoResidual::mean_signed_magnitude(enc.residual_yuv420)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
