#include "AuroraVideoMotion.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

namespace {

std::size_t frame_size(std::uint32_t w,std::uint32_t h) {
    return static_cast<std::size_t>(w)*h +
           2u*static_cast<std::size_t>(w/2)*(h/2);
}

Bytes make_structured(std::uint32_t w,std::uint32_t h,std::uint32_t phase) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            out[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (3u*x+5u*y+phase+((x/16u+phase)%5u)*7u)&255u);
    for(std::size_t i=0;i<us;++i) {
        out[ys+i]=static_cast<Byte>((80u+i+phase)&255u);
        out[ys+us+i]=static_cast<Byte>((170u+3u*i+phase)&255u);
    }
    return out;
}

Bytes make_noise(std::uint32_t w,std::uint32_t h,std::uint32_t seed) {
    Bytes out(frame_size(w,h));
    std::uint32_t s=seed;
    for(auto& b:out) {
        s=s*1664525u+1013904223u;
        b=static_cast<Byte>((s>>24)&255u);
    }
    return out;
}

std::uint64_t fnv1a(ByteView bytes,std::uint64_t h=1469598103934665603ull) {
    for(const auto b:bytes) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

void run(const char* name,ByteView cur,ByteView prev,
         std::uint32_t w,std::uint32_t h,int loops) {
    const double activity=AuroraVideoMotion::sparse_luma_mad(cur,prev,w,h,8);

    auto warm=AuroraVideoMotion::encode_mc8r4_adaptive(cur,prev,w,h,4.0,9);
    auto dec=AuroraVideoMotion::decode_mc8r4(
        warm.motion_map,warm.residual_yuv420,prev,w,h);
    if(dec.size()!=cur.size() || !std::equal(dec.begin(),dec.end(),cur.begin()))
        throw std::runtime_error(std::string(name)+": roundtrip failed");

    std::uint64_t fingerprint=0;
    const auto t0=Clock::now();
    for(int i=0;i<loops;++i) {
        auto enc=AuroraVideoMotion::encode_mc8r4_adaptive(cur,prev,w,h,4.0,9);
        if(i==0) {
            fingerprint=fnv1a(enc.motion_map);
            fingerprint=fnv1a(enc.residual_yuv420,fingerprint);
        }
    }
    const auto t1=Clock::now();
    const double seconds=std::chrono::duration<double>(t1-t0).count();
    std::cout<<"GRID25_BENCH"
             <<" name="<<name
             <<" activity="<<activity
             <<" route="<<(activity<=4.0 ? 9 : 25)
             <<" loops="<<loops
             <<" ms="<<(seconds*1000.0/loops)
             <<" calls_per_s="<<(loops/seconds)
             <<" fingerprint="<<fingerprint
             <<" motion_bytes="<<warm.motion_map.size()
             <<" residual_bytes="<<warm.residual_yuv420.size()
             <<"\n";
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        constexpr int loops=100;

        const auto base=make_structured(w,h,0);
        const auto low=make_structured(w,h,1);
        const auto noise_a=make_noise(w,h,0x12345678u);
        const auto noise_b=make_noise(w,h,0x9abcdef0u);

        run("static",base,base,w,h,loops);
        run("low_motion",low,base,w,h,loops);
        run("noise",noise_b,noise_a,w,h,loops);

        std::cout<<"AURORA_GRID25_SIMD_BENCH_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
