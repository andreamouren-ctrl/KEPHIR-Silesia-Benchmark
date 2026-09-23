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

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+frame_idx*2u+((x/64u+frame_idx)%7u)*3u+((y/48u+frame_idx)%5u)*2u)&255u);
    const auto cw=w/2, ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((96u+x+y+frame_idx)&255u);
            b[ys+us+i]=static_cast<Byte>((160u+2u*x+y+frame_idx*2u)&255u);
        }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2, ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    Bytes out(static_cast<std::size_t>(t.width)*t.height*3/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2, tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;

    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,out.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+src),tcw,out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+us+src),tcw,out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
    return out;
}

static double encode_parallel(ByteView cur,ByteView prev,const VideoTilePlan& plan,
                              std::uint32_t workers,std::uint64_t& packed_total) {
    std::vector<EncodedTile> out(plan.tiles.size());
    std::atomic<std::size_t> next{0};
    std::atomic<std::uint64_t> bytes{0};

    const auto t0=Clock::now();
    std::vector<std::thread> pool;
    pool.reserve(workers);

    for(std::uint32_t wi=0;wi<workers;++wi) {
        pool.emplace_back([&]{
            AuroraKhepriExp37MemoryAdapter khepri;
            while(true) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=plan.tiles.size()) break;
                const auto& tile=plan.tiles[i];
                auto c=extract_tile(cur,plan.frame_width,plan.frame_height,tile);
                auto p=extract_tile(prev,plan.frame_width,plan.frame_height,tile);
                auto mr=AuroraVideoMotion::encode_mc8r4(c,p,tile.width,tile.height);
                const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
                auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
                auto packed=khepri.encode(mapped);
                bytes.fetch_add(packed.size()+mr.motion_map.size()+1,std::memory_order_relaxed);
                out[i]=EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)};
            }
        });
    }
    for(auto& t:pool) t.join();
    const auto t1=Clock::now();
    packed_total=bytes.load(std::memory_order_relaxed);
    return std::chrono::duration<double>(t1-t0).count();
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Streaming4K);
        const auto plan=make_video_tile_plan(w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);

        for(const std::uint32_t workers : {1u,2u,4u,8u}) {
            std::uint64_t packed=0;
            const auto secs=encode_parallel(cur,prev,plan,workers,packed);
            std::cout<<"workers="<<workers
                     <<" seconds="<<secs
                     <<" fps="<<(1.0/secs)
                     <<" packed_bytes="<<packed<<"\n";
        }

        std::cout<<"AURORA_NATIVE_4K_PARALLEL_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
