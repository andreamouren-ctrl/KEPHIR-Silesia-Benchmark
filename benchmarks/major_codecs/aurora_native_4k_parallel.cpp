#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    Bytes packed;
};

struct RunResult {
    std::uint32_t workers{};
    double encode_seconds{};
    double decode_seconds{};
    double wall_seconds{};
    std::uint64_t packed_bytes{};
    bool roundtrip{};
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+frame_idx*2u+((x/64u+frame_idx)%7u)*3u+((y/48u+frame_idx)%5u)*2u)&255u);
    const auto cw=w/2; const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y) for(std::uint32_t x=0;x<cw;++x) {
        const auto i=static_cast<std::size_t>(y)*cw+x;
        b[ys+i]=static_cast<Byte>((96u+x+y+frame_idx)&255u);
        b[ys+us+i]=static_cast<Byte>((160u+2u*x+y+frame_idx*2u)&255u);
    }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    (void)fh;
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2u; const auto ch=fh/2u;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2u; const auto tch=t.height/2u;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    Bytes out(tys+2*tus);
    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    out.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(t.y/2u+y)*cw+t.x/2u;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+us+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
    return out;
}

static void paste_tile(Bytes& frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t,ByteView tile) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2u; const auto ch=fh/2u;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2u; const auto tch=t.height/2u;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(y)*t.width;
        const auto dst=static_cast<std::size_t>(t.y+y)*fw+t.x;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    frame.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(y)*tcw;
        const auto dst=static_cast<std::size_t>(t.y/2u+y)*cw+t.x/2u;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+dst));
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+tus+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+us+dst));
    }
}

template<class F>
static void parallel_for(std::size_t n,std::uint32_t workers,F&& fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::jthread> pool;
    pool.reserve(workers);
    for(std::uint32_t wi=0;wi<workers;++wi) {
        pool.emplace_back([&]{
            while(true) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=n) break;
                fn(i);
            }
        });
    }
}

static RunResult run_once(std::uint32_t workers,
                          ByteView cur,ByteView prev,
                          const VideoTilePlan& plan) {
    std::vector<EncodedTile> encoded(plan.tiles.size());
    std::atomic<std::uint64_t> packed_bytes{0};

    const auto wall0=Clock::now();
    const auto enc0=Clock::now();
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i){
        AuroraKhepriExp37MemoryAdapter khepri;
        const auto& tile=plan.tiles[i];
        auto c=extract_tile(cur,plan.frame_width,plan.frame_height,tile);
        auto p=extract_tile(prev,plan.frame_width,plan.frame_height,tile);
        auto mr=AuroraVideoMotion::encode_mc8r4(c,p,tile.width,tile.height);
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        auto packed=khepri.encode(mapped);
        packed_bytes.fetch_add(packed.size()+mr.motion_map.size()+1,std::memory_order_relaxed);
        encoded[i]=EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)};
    });
    const auto enc1=Clock::now();

    Bytes reconstructed(static_cast<std::size_t>(plan.frame_width)*plan.frame_height*3/2);
    const auto dec0=Clock::now();
    parallel_for(encoded.size(),workers,[&](std::size_t i){
        AuroraKhepriExp37MemoryAdapter khepri;
        const auto& et=encoded[i];
        auto p=extract_tile(prev,plan.frame_width,plan.frame_height,et.tile);
        auto mapped=khepri.decode(et.packed);
        auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
        auto tile=AuroraVideoMotion::decode_mc8r4(et.motion,residual,p,et.tile.width,et.tile.height);
        paste_tile(reconstructed,plan.frame_width,plan.frame_height,et.tile,tile);
    });
    const auto dec1=Clock::now();
    const auto wall1=Clock::now();

    return RunResult{
        workers,
        std::chrono::duration<double>(enc1-enc0).count(),
        std::chrono::duration<double>(dec1-dec0).count(),
        std::chrono::duration<double>(wall1-wall0).count(),
        packed_bytes.load(std::memory_order_relaxed),
        reconstructed==cur
    };
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Streaming4K);
        const auto plan=make_video_tile_plan(w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,8);
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);

        std::vector<RunResult> rows;
        for(const std::uint32_t workers: {1u,2u,4u,8u}) {
            auto r=run_once(workers,cur,prev,plan);
            if(!r.roundtrip) throw std::runtime_error("parallel 4K roundtrip failed");
            rows.push_back(r);
        }

        const auto serial=rows.front();
        std::cout<<"AURORA_NATIVE_4K_PARALLEL_PASS\n";
        for(const auto& r:rows) {
            std::cout<<"workers="<<r.workers
                     <<" encode_seconds="<<r.encode_seconds
                     <<" encode_fps="<<(1.0/r.encode_seconds)
                     <<" decode_seconds="<<r.decode_seconds
                     <<" decode_fps="<<(1.0/r.decode_seconds)
                     <<" wall_seconds="<<r.wall_seconds
                     <<" wall_fps="<<(1.0/r.wall_seconds)
                     <<" encode_speedup="<<(serial.encode_seconds/r.encode_seconds)
                     <<" payload_bytes="<<r.packed_bytes
                     <<"\n";
            if(r.packed_bytes!=serial.packed_bytes)
                throw std::runtime_error("parallel output size differs from serial");
        }
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
