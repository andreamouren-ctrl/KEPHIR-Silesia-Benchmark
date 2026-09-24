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

struct StageStats {
    double extract_s{};
    double motion_s{};
    double choose_s{};
    double map_s{};
    double khepri_s{};
    std::uint64_t tiles{};
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

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2, ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2, tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    Bytes out(tys+2*tus);
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
    return out;
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

static void run_case(const char* name,std::uint32_t fw,std::uint32_t fh) {
    constexpr std::uint32_t workers=4;
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,
                                         cfg.tile_halo,cfg.max_concurrent_tiles);
    const auto prev=make_frame(fw,fh,0);
    const auto cur=make_frame(fw,fh,1);

    std::vector<EncodedTile> encoded(plan.tiles.size());
    std::vector<AuroraKhepriExp37MemoryAdapter> khepri(workers);
    std::vector<StageStats> stats(workers);

    const auto wall0=Clock::now();
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        const auto& tile=plan.tiles[i];

        auto t0=Clock::now();
        auto c=extract_tile(cur,fw,fh,tile);
        auto p=extract_tile(prev,fw,fh,tile);
        auto t1=Clock::now();

        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
            c,p,tile.width,tile.height,4.0,9);
        auto t2=Clock::now();

        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto t3=Clock::now();

        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        auto t4=Clock::now();

        auto packed=khepri[worker].encode(mapped);
        auto t5=Clock::now();

        auto& s=stats[worker];
        s.extract_s+=std::chrono::duration<double>(t1-t0).count();
        s.motion_s+=std::chrono::duration<double>(t2-t1).count();
        s.choose_s+=std::chrono::duration<double>(t3-t2).count();
        s.map_s+=std::chrono::duration<double>(t4-t3).count();
        s.khepri_s+=std::chrono::duration<double>(t5-t4).count();
        ++s.tiles;

        encoded[i]=EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)};
    });
    const auto wall1=Clock::now();

    Bytes recon(static_cast<std::size_t>(fw)*fh*3/2);
    AuroraKhepriExp37MemoryAdapter decoder;
    for(const auto& et:encoded) {
        auto p=extract_tile(prev,fw,fh,et.tile);
        auto mapped=decoder.decode(et.packed);
        auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
        auto tile=AuroraVideoMotion::decode_mc8r4(
            et.motion,residual,p,et.tile.width,et.tile.height);
        paste_tile(recon,fw,fh,et.tile,tile);
    }
    if(recon!=cur)
        throw std::runtime_error(std::string("profile roundtrip mismatch at ")+name);

    StageStats sum;
    for(const auto& s:stats) {
        sum.extract_s+=s.extract_s;
        sum.motion_s+=s.motion_s;
        sum.choose_s+=s.choose_s;
        sum.map_s+=s.map_s;
        sum.khepri_s+=s.khepri_s;
        sum.tiles+=s.tiles;
    }

    const double cpu_total=sum.extract_s+sum.motion_s+sum.choose_s+sum.map_s+sum.khepri_s;
    const double wall_ms=std::chrono::duration<double,std::milli>(wall1-wall0).count();
    auto pct=[&](double x){ return cpu_total>0.0 ? 100.0*x/cpu_total : 0.0; };

    std::uint64_t packed_bytes=0;
    for(const auto& e:encoded) packed_bytes+=e.packed.size()+e.motion.size()+1;

    std::cout<<"ENCODE_PROFILE_PASS"
             <<" name="<<name
             <<" workers="<<workers
             <<" tiles="<<sum.tiles
             <<" wall_ms="<<wall_ms
             <<" wall_fps="<<(1000.0/wall_ms)
             <<" extract_cpu_ms="<<(sum.extract_s*1000.0)
             <<" extract_pct="<<pct(sum.extract_s)
             <<" motion_cpu_ms="<<(sum.motion_s*1000.0)
             <<" motion_pct="<<pct(sum.motion_s)
             <<" choose_cpu_ms="<<(sum.choose_s*1000.0)
             <<" choose_pct="<<pct(sum.choose_s)
             <<" map_cpu_ms="<<(sum.map_s*1000.0)
             <<" map_pct="<<pct(sum.map_s)
             <<" khepri_cpu_ms="<<(sum.khepri_s*1000.0)
             <<" khepri_pct="<<pct(sum.khepri_s)
             <<" packed_bytes="<<packed_bytes
             <<" lossless=1"
             <<"\n";
}

int main() {
    try {
        std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";
        run_case("1080p",1920,1080);
        run_case("1440p",2560,1440);
        run_case("4K",3840,2160);
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
