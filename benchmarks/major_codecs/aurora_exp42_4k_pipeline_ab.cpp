#if defined(AURORA_KHEPRI_EXP42)
#include "AuroraKhepriExp42MemoryAdapter.h"
using PipelineBackend = aurora::media::AuroraKhepriExp42MemoryAdapter;
static constexpr const char* kPipelineBackend = "EXP42_DIST_LOG_CACHE";
#else
#include "AuroraKhepriExp40MemoryAdapter.h"
using PipelineBackend = aurora::media::AuroraKhepriExp40MemoryAdapter;
static constexpr const char* kPipelineBackend = "EXP40_SHARED_CACHE";
#endif
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include "AuroraWorkerAutotune.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <future>
#include <iostream>
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

struct WorkerScratch {
    Bytes current_tile;
    Bytes previous_tile;
    PipelineBackend khepri;
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+frame_idx*2u+((x/64u+frame_idx)%7u)*3u+
                 ((y/48u+frame_idx)%5u)*2u)&255u);
    const auto cw=w/2, ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((96u+x+y+frame_idx)&255u);
            b[ys+us+i]=static_cast<Byte>((160u+2u*x+y+frame_idx*2u)&255u);
        }
    return b;
}

static void extract_tile_into(ByteView frame,std::uint32_t fw,std::uint32_t fh,
                              const VideoTile& t,Bytes& out) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2, ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2, tch=t.height/2;
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

static void paste_tile(Bytes& frame,std::uint32_t fw,std::uint32_t fh,
                       const VideoTile& t,ByteView tile) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2, ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2, tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    (void)ch;
    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(y)*t.width;
        const auto dst=static_cast<std::size_t>(t.y+y)*fw+t.x;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    frame.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto dst=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2;
        const auto src=static_cast<std::size_t>(y)*tcw;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+dst));
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+tus+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+us+dst));
    }
}

static EncodedTile encode_one(ByteView cur,ByteView prev,
                              std::uint32_t fw,std::uint32_t fh,const VideoTile& tile,
                              WorkerScratch& scratch) {
    extract_tile_into(cur,fw,fh,tile,scratch.current_tile);
    extract_tile_into(prev,fw,fh,tile,scratch.previous_tile);
    auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
        scratch.current_tile,scratch.previous_tile,tile.width,tile.height,4.0,9);
    const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
    auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
    auto packed=scratch.khepri.encode(mapped);
    return EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)};
}

static Bytes decode_one(const EncodedTile& et,ByteView prev,std::uint32_t fw,std::uint32_t fh,
                        WorkerScratch& scratch) {
    extract_tile_into(prev,fw,fh,et.tile,scratch.previous_tile);
    auto mapped=scratch.khepri.decode(et.packed);
    auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
    return AuroraVideoMotion::decode_mc8r4(
        et.motion,residual,scratch.previous_tile,et.tile.width,et.tile.height);
}

template<class Fn>
static void parallel_for(std::size_t count,std::uint32_t workers,Fn fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for(std::uint32_t w=0;w<workers;++w) {
        pool.emplace_back([&,w]{
            for(;;) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=count) break;
                fn(i,w);
            }
        });
    }
    for(auto& t:pool) t.join();
}

struct CaseTiming {
    double encode_seconds{};
    double decode_seconds{};
    double total_seconds{};
    std::uint64_t packed_bytes{};
};

static CaseTiming run_case(const char* label,std::uint32_t workers,
                           ByteView cur,ByteView prev,const VideoTilePlan& plan) {
    std::vector<EncodedTile> encoded(plan.tiles.size());
    std::vector<WorkerScratch> encode_workers(workers);
    std::vector<WorkerScratch> decode_workers(workers);
    const auto max_tile_bytes=
        static_cast<std::size_t>(plan.tile_width)*plan.tile_height*3/2;
    for(auto& w:encode_workers) {
        w.current_tile.reserve(max_tile_bytes);
        w.previous_tile.reserve(max_tile_bytes);
    }
    for(auto& w:decode_workers)
        w.previous_tile.reserve(max_tile_bytes);

    const auto e0=Clock::now();
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        encoded[i]=encode_one(cur,prev,plan.frame_width,plan.frame_height,plan.tiles[i],
                              encode_workers[worker]);
    });
    const auto e1=Clock::now();

    std::vector<Bytes> decoded(plan.tiles.size());
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        decoded[i]=decode_one(encoded[i],prev,plan.frame_width,plan.frame_height,
                              decode_workers[worker]);
    });
    const auto d1=Clock::now();

    Bytes recon(static_cast<std::size_t>(plan.frame_width)*plan.frame_height*3/2);
    for(std::size_t i=0;i<decoded.size();++i)
        paste_tile(recon,plan.frame_width,plan.frame_height,plan.tiles[i],decoded[i]);
    if(!std::equal(recon.begin(),recon.end(),cur.begin(),cur.end()))
        throw std::runtime_error(std::string("parallel reconstruction mismatch at ")+label);

    std::uint64_t packed=0;
    for(const auto& e:encoded) packed+=e.packed.size()+e.motion.size()+1;

    const double enc=std::chrono::duration<double>(e1-e0).count();
    const double dec=std::chrono::duration<double>(d1-e1).count();
    const double total=enc+dec;
    std::cout<<"PARALLEL_PASS"
             <<" name="<<label
             <<" workers="<<workers
             <<" encode_seconds="<<enc
             <<" encode_fps="<<(1.0/enc)
             <<" decode_seconds="<<dec
             <<" decode_fps="<<(1.0/dec)
             <<" total_seconds="<<total
             <<" total_fps="<<(1.0/total)
             <<" packed_bytes="<<packed<<"\n";
    return CaseTiming{enc,dec,total,packed};
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(
            w,h,cfg.tile_width,cfg.tile_height,
            cfg.tile_halo,cfg.max_concurrent_tiles);
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);

        std::cout<<"backend="<<kPipelineBackend
                 <<" hardware_concurrency="<<std::thread::hardware_concurrency()
                 <<"\n";
        const auto timing=run_case("4K",4,cur,prev,plan);
        std::cout<<"AURORA_EXP42_4K_PIPELINE_PASS"
                 <<" backend="<<kPipelineBackend
                 <<" total_ms="<<(timing.total_seconds*1000.0)
                 <<" packed_bytes="<<timing.packed_bytes
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
