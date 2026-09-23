#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

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

template<class F>
static void parallel_for(std::size_t n,std::uint32_t workers,F&& fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::jthread> pool;
    for(std::uint32_t w=0;w<workers;++w) pool.emplace_back([&]{
        while(true) {
            const auto i=next.fetch_add(1,std::memory_order_relaxed);
            if(i>=n) break;
            fn(i);
        }
    });
}

struct Result {
    std::uint32_t tw{},th{};
    std::size_t tiles{};
    double seconds{};
    std::uint64_t payload{};
};

static Result run_case(std::uint32_t tw,std::uint32_t th,ByteView cur,ByteView prev) {
    constexpr std::uint32_t fw=3840,fh=2160;
    const auto plan=make_video_tile_plan(fw,fh,tw,th,8,4);
    std::atomic<std::uint64_t> payload{0};
    const auto t0=Clock::now();
    parallel_for(plan.tiles.size(),4,[&](std::size_t i){
        AuroraKhepriExp37MemoryAdapter khepri;
        const auto& tile=plan.tiles[i];
        auto c=extract_tile(cur,fw,fh,tile);
        auto p=extract_tile(prev,fw,fh,tile);
        auto mr=AuroraVideoMotion::encode_mc8r4(c,p,tile.width,tile.height);
        auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        auto packed=khepri.encode(mapped);
        payload.fetch_add(packed.size()+mr.motion_map.size()+1,std::memory_order_relaxed);
    });
    const auto t1=Clock::now();
    return Result{tw,th,plan.tiles.size(),std::chrono::duration<double>(t1-t0).count(),payload.load()};
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);
        std::vector<Result> rows;
        rows.push_back(run_case(256,240,cur,prev));
        rows.push_back(run_case(384,240,cur,prev));
        rows.push_back(run_case(512,480,cur,prev));
        const auto base=rows.front();
        std::cout<<"AURORA_NATIVE_4K_TILE_GEOMETRY_PASS\n";
        for(const auto& r:rows) {
            std::cout<<"tile="<<r.tw<<"x"<<r.th
                     <<" tiles="<<r.tiles
                     <<" seconds="<<r.seconds
                     <<" fps="<<(1.0/r.seconds)
                     <<" speedup="<<(base.seconds/r.seconds)
                     <<" payload_bytes="<<r.payload
                     <<" delta_bytes="<<static_cast<std::int64_t>(r.payload)-static_cast<std::int64_t>(base.payload)
                     <<" delta_percent="<<(100.0*(static_cast<double>(r.payload)-base.payload)/base.payload)
                     <<"\n";
        }
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
