#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoResidual.h"
#include <chrono>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes make_frame(std::uint32_t w,std::uint32_t h,int shift) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((x*3+y*5+shift)&255);
    for(std::size_t i=0;i<us;++i) {
        b[ys+i]=static_cast<Byte>((80+(i%53)+shift)&255);
        b[ys+us+i]=static_cast<Byte>((170+(i%71)+shift)&255);
    }
    return b;
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        constexpr int loops=12;
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,2);
        AuroraKhepriExp37MemoryAdapter khepri;

        auto run_full=[&]() {
            const auto motion=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
            const auto mode=AuroraVideoResidual::choose_mode(motion.residual_yuv420);
            const auto mapped=AuroraVideoResidual::map(motion.residual_yuv420,mode);
            const auto packed=khepri.encode(mapped);
            const auto unpacked=khepri.decode(packed);
            const auto residual=AuroraVideoResidual::unmap(unpacked,mode);
            const auto reconstructed=AuroraVideoMotion::decode_mc8r4(
                motion.motion_map,residual,prev,w,h);
            if(reconstructed!=cur)
                throw std::runtime_error("full native video pipeline roundtrip failed");
            return std::pair<std::size_t,std::size_t>{packed.size(),motion.motion_map.size()};
        };

        auto run_adaptive=[&]() {
            const auto motion=AuroraVideoMotion::encode_mc8r4_adaptive(cur,prev,w,h,4.0,9);
            const auto mode=AuroraVideoResidual::choose_mode(motion.residual_yuv420);
            const auto mapped=AuroraVideoResidual::map(motion.residual_yuv420,mode);
            const auto packed=khepri.encode(mapped);
            const auto unpacked=khepri.decode(packed);
            const auto residual=AuroraVideoResidual::unmap(unpacked,mode);
            const auto reconstructed=AuroraVideoMotion::decode_mc8r4(
                motion.motion_map,residual,prev,w,h);
            if(reconstructed!=cur)
                throw std::runtime_error("adaptive native video pipeline roundtrip failed");
            return std::pair<std::size_t,std::size_t>{packed.size(),motion.motion_map.size()};
        };

        const auto full_once=run_full();
        const auto adaptive_once=run_adaptive();

        using clock=std::chrono::steady_clock;
        auto t0=clock::now();
        for(int i=0;i<loops;++i) (void)run_full();
        auto t1=clock::now();
        for(int i=0;i<loops;++i) (void)run_adaptive();
        auto t2=clock::now();

        const double full_ms=std::chrono::duration<double,std::milli>(t1-t0).count()/loops;
        const double adaptive_ms=std::chrono::duration<double,std::milli>(t2-t1).count()/loops;
        const double full_fps=full_ms>0.0 ? 1000.0/full_ms : 0.0;
        const double adaptive_fps=adaptive_ms>0.0 ? 1000.0/adaptive_ms : 0.0;
        const double speedup=adaptive_ms>0.0 ? full_ms/adaptive_ms : 0.0;
        const auto activity=AuroraVideoMotion::sparse_luma_mad(cur,prev,w,h);

        std::cout<<"NATIVE_VIDEO_PIPELINE_PASS"
                 <<" activity="<<activity
                 <<" full_khepri_bytes="<<full_once.first
                 <<" adaptive_khepri_bytes="<<adaptive_once.first
                 <<" motion_map_bytes="<<adaptive_once.second
                 <<" full_ms="<<full_ms
                 <<" adaptive_ms="<<adaptive_ms
                 <<" full_fps="<<full_fps
                 <<" adaptive_fps="<<adaptive_fps
                 <<" speedup_x="<<speedup
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
