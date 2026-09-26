#include "AuroraVideoMotion.h"
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

static Bytes make_previous(std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t cs=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*cs);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            out[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*13u+y*7u+((x*y)%31u)*5u+((x/9u)^(y/7u))*17u)&255u);
    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            out[ys+i]=static_cast<Byte>((61u+x*3u+y*11u+((x*y)%19u)*7u)&255u);
            out[ys+cs+i]=static_cast<Byte>((173u+x*9u+y*5u+((x+y)%23u)*3u)&255u);
        }
    return out;
}

static Bytes make_current(ByteView prev,std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t cs=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*cs);

    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=0;x<w;++x) {
            const int dx=(y<h/2)?-1:3;
            const int dy=(x<w/2)?1:-3;
            const int sx=static_cast<int>(x)+dx;
            const int sy=static_cast<int>(y)+dy;
            out[static_cast<std::size_t>(y)*w+x]=
                (sx>=0 && sy>=0 && sx<static_cast<int>(w) && sy<static_cast<int>(h))
                ? prev[static_cast<std::size_t>(sy)*w+static_cast<std::uint32_t>(sx)]
                : static_cast<Byte>((x*29u+y*31u+7u)&255u);
        }
    }

    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            out[ys+i]=static_cast<Byte>((prev[ys+i]+37u)&255u);
            out[ys+cs+i]=static_cast<Byte>((prev[ys+cs+i]+83u)&255u);
        }
    return out;
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        const auto prev=make_previous(w,h);
        const auto cur=make_current(prev,w,h);

        const auto variants=AuroraVideoMotion::encode_mc8r4_h3_variants(cur,prev,w,h);
        const auto floor=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Floor);
        const auto trunc=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Trunc);

        if(variants.motion_map!=floor.motion_map ||
           variants.motion_map!=trunc.motion_map)
            throw std::runtime_error("one-pass H3 motion mismatch");
        if(variants.residual_floor_yuv420!=floor.residual_yuv420)
            throw std::runtime_error("one-pass FLOOR residual mismatch");
        if(variants.residual_trunc_yuv420!=trunc.residual_yuv420)
            throw std::runtime_error("one-pass TRUNC residual mismatch");

        const auto floor_dec=AuroraVideoMotion::decode_mc8r4_dense(
            variants.motion_map,variants.residual_floor_yuv420,prev,w,h,
            DenseChromaPolicy::Floor);
        const auto trunc_dec=AuroraVideoMotion::decode_mc8r4_dense(
            variants.motion_map,variants.residual_trunc_yuv420,prev,w,h,
            DenseChromaPolicy::Trunc);
        if(floor_dec!=cur || trunc_dec!=cur)
            throw std::runtime_error("one-pass H3 roundtrip mismatch");

        constexpr int loops=12;
        double one_s=0.0,two_s=0.0;
        for(int i=0;i<loops;++i) {
            const auto t0=Clock::now();
            const auto v=AuroraVideoMotion::encode_mc8r4_h3_variants(cur,prev,w,h);
            const auto t1=Clock::now();
            const auto f=AuroraVideoMotion::encode_mc8r4_h3(
                cur,prev,w,h,DenseChromaPolicy::Floor);
            const auto t=AuroraVideoMotion::encode_mc8r4_h3(
                cur,prev,w,h,DenseChromaPolicy::Trunc);
            const auto t2=Clock::now();

            if(v.motion_map!=f.motion_map || v.motion_map!=t.motion_map)
                throw std::runtime_error("timed H3 mismatch");

            one_s+=std::chrono::duration<double>(t1-t0).count();
            two_s+=std::chrono::duration<double>(t2-t1).count();
        }
        one_s/=loops;
        two_s/=loops;

        std::cout<<"AURORA_H3_VARIANTS_PASS"
                 <<" blocks="<<variants.motion_map.size()
                 <<" one_pass_ms="<<(one_s*1000.0)
                 <<" two_search_ms="<<(two_s*1000.0)
                 <<" speedup_x="<<(one_s>0.0 ? two_s/one_s : 0.0)
                 <<" floor_equals_trunc="
                 <<(variants.residual_floor_yuv420==variants.residual_trunc_yuv420 ? 1 : 0)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
