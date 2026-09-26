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
                (x*3u+y*5u+phase+((x/32u+phase)%7u)*3u+
                 ((y/24u+phase)%5u)*2u)&255u);

    for(std::size_t i=0;i<us;++i) {
        out[ys+i]=static_cast<Byte>((96u+i+phase)&255u);
        out[ys+us+i]=static_cast<Byte>((160u+3u*i+phase)&255u);
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
    // Warm-up.
    auto warm=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
    const auto dec=AuroraVideoMotion::decode_mc8r4(
        warm.motion_map,warm.residual_yuv420,prev,w,h);
    if(dec.size()!=cur.size() || !std::equal(dec.begin(),dec.end(),cur.begin()))
        throw std::runtime_error(std::string(name)+": roundtrip failed");

    std::uint64_t fingerprint=0;
    const auto t0=Clock::now();
    for(int i=0;i<loops;++i) {
        auto enc=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
        if(i==0) {
            fingerprint=fnv1a(enc.motion_map);
            fingerprint=fnv1a(enc.residual_yuv420,fingerprint);
        }
    }
    const auto t1=Clock::now();

    const double seconds=std::chrono::duration<double>(t1-t0).count();
    const double per_call_ms=(seconds*1000.0)/loops;
    const double calls_per_s=loops/seconds;

    std::cout<<"MOTION_BENCH"
             <<" name="<<name
             <<" loops="<<loops
             <<" ms="<<per_call_ms
             <<" calls_per_s="<<calls_per_s
             <<" fingerprint="<<fingerprint
             <<" motion_bytes="<<warm.motion_map.size()
             <<" residual_bytes="<<warm.residual_yuv420.size()
             <<"\n";
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        constexpr int loops=80;

        const auto base=make_structured(w,h,0);
        const auto low=make_structured(w,h,1);
        const auto noise_a=make_noise(w,h,0x12345678u);
        const auto noise_b=make_noise(w,h,0x9abcdef0u);

        run("static",base,base,w,h,loops);
        run("low_motion",low,base,w,h,loops);
        run("noise",noise_b,noise_a,w,h,loops);

        std::cout<<"AURORA_EXACT_MOTION_FASTPATH_BENCH_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
