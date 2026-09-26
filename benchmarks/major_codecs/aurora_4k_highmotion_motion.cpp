#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

namespace {

struct TileResult {
    Bytes motion;
    Bytes residual;
};

Bytes make_noise_frame(std::uint32_t w,std::uint32_t h,std::uint32_t seed) {
    const std::size_t bytes=static_cast<std::size_t>(w)*h*3/2;
    Bytes out(bytes);
    std::uint32_t s=seed;
    for(auto& b:out) {
        s=s*1664525u+1013904223u;
        b=static_cast<Byte>((s>>24)&255u);
    }
    return out;
}

void extract_tile_into(ByteView frame,std::uint32_t fw,std::uint32_t fh,
                       const VideoTile& t,Bytes& out) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2;
    const auto ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2;
    const auto tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    out.resize(tys+2*tus);

    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    out.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+us+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
}

std::uint64_t fnv1a(ByteView b,std::uint64_t h=1469598103934665603ull) {
    for(const auto v:b) {
        h^=static_cast<std::uint64_t>(v);
        h*=1099511628211ull;
    }
    return h;
}

template<class Fn>
void parallel_for(std::size_t count,std::uint32_t workers,Fn fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for(std::uint32_t worker=0;worker<workers;++worker) {
        pool.emplace_back([&,worker]{
            for(;;) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=count) break;
                fn(i,worker);
            }
        });
    }
    for(auto& t:pool) t.join();
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t fw=3840,fh=2160;
        constexpr std::uint32_t workers=4;
        constexpr int loops=3;

        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(
            fw,fh,cfg.tile_width,cfg.tile_height,
            cfg.tile_halo,cfg.max_concurrent_tiles);

        const auto prev=make_noise_frame(fw,fh,0x12345678u);
        const auto cur=make_noise_frame(fw,fh,0x9abcdef0u);

        std::vector<std::vector<Bytes>> current(workers),previous(workers);
        for(std::uint32_t w=0;w<workers;++w) {
            current[w].resize(1);
            previous[w].resize(1);
        }

        std::vector<TileResult> results(plan.tiles.size());
        double total_s=0.0;
        std::uint64_t fingerprint=0;

        for(int loop=0;loop<loops;++loop) {
            const auto t0=Clock::now();
            parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
                auto& ct=current[worker][0];
                auto& pt=previous[worker][0];
                const auto& tile=plan.tiles[i];
                extract_tile_into(cur,fw,fh,tile,ct);
                extract_tile_into(prev,fw,fh,tile,pt);

                // Random independent frames force the adaptive router into the
                // full 25-candidate high-activity path.
                auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
                    ct,pt,tile.width,tile.height,4.0,9);
                results[i]={std::move(mr.motion_map),std::move(mr.residual_yuv420)};
            });
            total_s+=std::chrono::duration<double>(Clock::now()-t0).count();

            if(loop==0) {
                fingerprint=1469598103934665603ull;
                for(const auto& r:results) {
                    fingerprint=fnv1a(r.motion,fingerprint);
                    fingerprint=fnv1a(r.residual,fingerprint);
                }
            }
        }

        const double avg=total_s/loops;
        std::cout<<"AURORA_4K_HIGHMOTION_MOTION_PASS"
                 <<" tiles="<<plan.tiles.size()
                 <<" workers="<<workers
                 <<" encode_ms="<<(avg*1000.0)
                 <<" fps="<<(1.0/avg)
                 <<" fingerprint="<<fingerprint
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
