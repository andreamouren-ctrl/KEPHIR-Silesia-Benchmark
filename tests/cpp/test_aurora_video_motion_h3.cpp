#include "AuroraVideoMotion.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

namespace {

std::uint64_t fnv1a(ByteView bytes) {
    std::uint64_t h=1469598103934665603ull;
    for(const auto b:bytes) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

Byte pattern(std::uint32_t x,std::uint32_t y,std::uint32_t seed) {
    return static_cast<Byte>(
        (x*13u+y*7u+seed*19u+
         ((x/11u+seed)%7u)*17u+
         ((y/9u+seed)%5u)*23u)&255u);
}

Bytes make_previous(std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*us);

    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            out[static_cast<std::size_t>(y)*w+x]=pattern(x,y,1);

    const auto cw=w/2;
    const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            out[ys+i]=pattern(x,y,3);
            out[ys+us+i]=pattern(x,y,5);
        }
    return out;
}

Bytes make_current(ByteView prev,std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(prev.begin(),prev.end());

    // Force a dominant odd luma displacement of -1 on all non-border pixels.
    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=1;x<w;++x) {
            out[static_cast<std::size_t>(y)*w+x]=
                prev[static_cast<std::size_t>(y)*w+(x-1)];
        }
        out[static_cast<std::size_t>(y)*w]=pattern(0,y,9);
    }

    // Chroma intentionally uses a different deterministic transform so FLOOR
    // and TRUNC produce different residual fingerprints for negative odd motion.
    const auto cw=w/2;
    const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y) {
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            out[ys+i]=static_cast<Byte>((prev[ys+i]+31u)&255u);
            out[ys+us+i]=static_cast<Byte>((prev[ys+us+i]+47u)&255u);
        }
    }
    return out;
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        const auto prev=make_previous(w,h);
        const auto cur=make_current(prev,w,h);

        const auto dense=AuroraVideoMotion::dense_candidates(4);
        if(dense.size()!=81)
            throw std::runtime_error("dense candidate count");
        if(dense.front()!=std::pair<int,int>{0,0})
            throw std::runtime_error("dense candidate zero ordering");

        const auto floor=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Floor);
        const auto trunc=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Trunc);

        if(floor.motion_map!=trunc.motion_map)
            throw std::runtime_error("chroma policy changed luma motion decisions");

        const auto floor_dec=AuroraVideoMotion::decode_mc8r4_dense(
            floor.motion_map,floor.residual_yuv420,prev,w,h,
            DenseChromaPolicy::Floor);
        const auto trunc_dec=AuroraVideoMotion::decode_mc8r4_dense(
            trunc.motion_map,trunc.residual_yuv420,prev,w,h,
            DenseChromaPolicy::Trunc);

        if(floor_dec!=cur || trunc_dec!=cur)
            throw std::runtime_error("native H3 roundtrip");

        std::size_t odd_blocks=0;
        for(const auto idx:floor.motion_map) {
            if(idx>=dense.size())
                throw std::runtime_error("native H3 dense index");
            const auto [dx,dy]=dense[idx];
            if((dx&1)||(dy&1))
                ++odd_blocks;
        }
        if(odd_blocks==0)
            throw std::runtime_error("native H3 never selected odd displacement");

        std::cout<<"AURORA_NATIVE_H3_PASS"
                 <<" blocks="<<floor.motion_map.size()
                 <<" odd_blocks="<<odd_blocks
                 <<" motion_fp="<<fnv1a(floor.motion_map)
                 <<" floor_residual_fp="<<fnv1a(floor.residual_yuv420)
                 <<" trunc_residual_fp="<<fnv1a(trunc.residual_yuv420)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
