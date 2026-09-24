#include "AuroraVideoMotion.h"
#include "AuroraVideoResidual.h"
#include <chrono>
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

        const double low_activity=AuroraVideoMotion::sparse_luma_mad(cur,prev,w,h);
        if(low_activity>4.0) throw std::runtime_error("low-motion classifier");

        const auto adaptive=AuroraVideoMotion::encode_mc8r4_adaptive(cur,prev,w,h,4.0,9);
        const auto adaptive_dec=AuroraVideoMotion::decode_mc8r4(
            adaptive.motion_map,adaptive.residual_yuv420,prev,w,h);
        if(adaptive_dec!=cur) throw std::runtime_error("adaptive MC8R4 roundtrip");

        // A deliberately high-activity frame must retain the full 25-candidate path.
        auto busy=cur;
        for(std::size_t i=0;i<static_cast<std::size_t>(w)*h;++i)
            busy[i]=static_cast<Byte>((busy[i]+((i*37u)&255u))&255u);
        const double high_activity=AuroraVideoMotion::sparse_luma_mad(busy,prev,w,h);
        if(high_activity<=4.0) throw std::runtime_error("high-motion classifier");
        const auto adaptive_busy=AuroraVideoMotion::encode_mc8r4_adaptive(busy,prev,w,h,4.0,9);
        const auto full_busy=AuroraVideoMotion::encode_mc8r4(busy,prev,w,h);
        if(adaptive_busy.motion_map!=full_busy.motion_map ||
           adaptive_busy.residual_yuv420!=full_busy.residual_yuv420)
            throw std::runtime_error("high-motion adaptive path must equal full search");

        using clock=std::chrono::steady_clock;
        constexpr int loops=20;
        auto t0=clock::now();
        for(int i=0;i<loops;++i) (void)AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
        auto t1=clock::now();
        for(int i=0;i<loops;++i) (void)AuroraVideoMotion::encode_mc8r4_adaptive(cur,prev,w,h,4.0,9);
        auto t2=clock::now();
        const double full_ms=std::chrono::duration<double,std::milli>(t1-t0).count()/loops;
        const double adaptive_ms=std::chrono::duration<double,std::milli>(t2-t1).count()/loops;

        const auto mode=AuroraVideoResidual::choose_mode(enc.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(enc.residual_yuv420,mode);
        auto un=AuroraVideoResidual::unmap(mapped,mode);
        if(un!=enc.residual_yuv420)
            throw std::runtime_error("motion residual map roundtrip");

        std::cout<<"VIDEO_MOTION_CPP_PASS blocks="<<enc.motion_map.size()
                 <<" mean_residual="<<AuroraVideoResidual::mean_signed_magnitude(enc.residual_yuv420)
                 <<" low_activity="<<low_activity
                 <<" high_activity="<<high_activity
                 <<" full_ms="<<full_ms
                 <<" adaptive_ms="<<adaptive_ms
                 <<" speedup_x="<<(adaptive_ms>0.0 ? full_ms/adaptive_ms : 0.0)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
