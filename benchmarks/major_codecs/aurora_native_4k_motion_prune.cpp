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
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t f) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+f*2u+((x/64u+f)%7u)*3u+((y/48u+f)%5u)*2u)&255u);
    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((96u+x+y+f)&255u);
            b[ys+us+i]=static_cast<Byte>((160u+2u*x+y+2u*f)&255u);
        }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2,ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    Bytes out(static_cast<std::size_t>(t.width)*t.height*3/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2,tch=t.height/2;
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

static void bench(ByteView cur,ByteView prev,const VideoTilePlan& plan,
                  std::size_t candidates,std::uint32_t workers) {
    std::atomic<std::size_t> next{0};
    std::atomic<std::uint64_t> packed{0};
    const auto t0=Clock::now();
    std::vector<std::thread> pool;
    for(std::uint32_t wi=0;wi<workers;++wi) {
        pool.emplace_back([&]{
            AuroraKhepriExp37MemoryAdapter k;
            while(true) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=plan.tiles.size()) break;
                const auto& tile=plan.tiles[i];
                auto c=extract_tile(cur,plan.frame_width,plan.frame_height,tile);
                auto p=extract_tile(prev,plan.frame_width,plan.frame_height,tile);
                auto mr=AuroraVideoMotion::encode_mc8r4_limited(c,p,tile.width,tile.height,candidates);
                const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
                auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
                auto enc=k.encode(mapped);
                packed.fetch_add(enc.size()+mr.motion_map.size()+1,std::memory_order_relaxed);
            }
        });
    }
    for(auto& t:pool) t.join();
    const double sec=std::chrono::duration<double>(Clock::now()-t0).count();
    std::cout<<"candidates="<<candidates
             <<" workers="<<workers
             <<" seconds="<<sec
             <<" fps="<<(1.0/sec)
             <<" packed_bytes="<<packed.load()<<"\n";
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Streaming4K);
        const auto plan=make_video_tile_plan(w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,4);
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);
        for(const std::size_t c : {25u,13u,9u})
            bench(cur,prev,plan,c,4);
        std::cout<<"AURORA_NATIVE_4K_MOTION_PRUNE_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
