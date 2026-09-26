#include "AuroraVideoMotion.h"
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

namespace {

std::size_t frame_size(std::uint32_t w,std::uint32_t h) {
    return static_cast<std::size_t>(w)*h +
           2u*static_cast<std::size_t>(w/2)*(h/2);
}

std::uint64_t scalar_sad8x8(ByteView cur,ByteView prev,
                            std::uint32_t stride,
                            std::uint32_t cx,std::uint32_t cy,
                            std::uint32_t px,std::uint32_t py) {
    std::uint64_t sum=0;
    for(std::uint32_t yy=0;yy<8;++yy)
        for(std::uint32_t xx=0;xx<8;++xx) {
            const auto ci=static_cast<std::size_t>(cy+yy)*stride+(cx+xx);
            const auto pi=static_cast<std::size_t>(py+yy)*stride+(px+xx);
            sum += static_cast<std::uint64_t>(
                std::abs(static_cast<int>(cur[ci])-static_cast<int>(prev[pi])));
        }
    return sum;
}

Bytes reference_motion_map(ByteView cur,ByteView prev,
                           std::uint32_t w,std::uint32_t h,
                           std::size_t max_candidates) {
    constexpr std::uint32_t block=8;
    const auto cand=AuroraVideoMotion::candidates(4);
    const auto count=std::min(max_candidates,cand.size());

    Bytes out;
    out.reserve(static_cast<std::size_t>(w/block)*(h/block));

    for(std::uint32_t by=0;by<h;by+=block) {
        for(std::uint32_t bx=0;bx<w;bx+=block) {
            int best_idx=-1;
            std::uint64_t best_cost=std::numeric_limits<std::uint64_t>::max();

            for(std::size_t i=0;i<count;++i) {
                const auto [dx,dy]=cand[i];
                const int sx=static_cast<int>(bx)+dx;
                const int sy=static_cast<int>(by)+dy;
                if(sx<0 || sy<0 ||
                   sx+static_cast<int>(block)>static_cast<int>(w) ||
                   sy+static_cast<int>(block)>static_cast<int>(h))
                    continue;

                const auto cost=scalar_sad8x8(
                    cur,prev,w,bx,by,
                    static_cast<std::uint32_t>(sx),
                    static_cast<std::uint32_t>(sy));

                // This is the historical exhaustive tie rule.
                if(cost<best_cost) {
                    best_cost=cost;
                    best_idx=static_cast<int>(i);
                }
            }

            if(best_idx<0)
                throw std::runtime_error("reference motion search found no candidate");
            out.push_back(static_cast<Byte>(best_idx));
        }
    }

    return out;
}

Bytes make_pattern(std::uint32_t w,std::uint32_t h,std::uint32_t seed) {
    Bytes out(frame_size(w,h));
    std::uint32_t s=seed;
    for(auto& b:out) {
        s = s*1664525u + 1013904223u;
        b=static_cast<Byte>((s>>24)&0xffu);
    }
    return out;
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

void verify_case(const char* name,ByteView cur,ByteView prev,
                 std::uint32_t w,std::uint32_t h,std::size_t limit) {
    const auto expected=reference_motion_map(cur,prev,w,h,limit);
    const auto actual=AuroraVideoMotion::encode_mc8r4_limited(cur,prev,w,h,limit);

    if(actual.motion_map!=expected)
        throw std::runtime_error(std::string(name)+": motion map changed");

    const auto decoded=AuroraVideoMotion::decode_mc8r4(
        actual.motion_map,actual.residual_yuv420,prev,w,h);
    if(!std::equal(decoded.begin(),decoded.end(),cur.begin(),cur.end()))
        throw std::runtime_error(std::string(name)+": lossless roundtrip failed");
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=128,h=96;

        const auto identical=make_structured(w,h,3);
        verify_case("identical-full",identical,identical,w,h,25);
        verify_case("identical-short",identical,identical,w,h,9);

        const auto prev=make_structured(w,h,0);
        const auto cur=make_structured(w,h,2);
        verify_case("structured-full",cur,prev,w,h,25);
        verify_case("structured-short",cur,prev,w,h,9);

        const auto random_prev=make_pattern(w,h,0x12345678u);
        const auto random_cur=make_pattern(w,h,0x9abcdef0u);
        verify_case("random-full",random_cur,random_prev,w,h,25);
        verify_case("random-short",random_cur,random_prev,w,h,9);

        std::cout<<"AURORA_EXACT_MOTION_FASTPATH_EQUIVALENCE_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
