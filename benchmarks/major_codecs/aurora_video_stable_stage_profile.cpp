#include "AuroraKhepriFastDMemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <numeric>
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
    double extract{};
    double motion{};
    double choose{};
    double map{};
    double fastd{};
};

struct FrameStats {
    double wall_ms{};
    double extract_cpu_ms{};
    double motion_cpu_ms{};
    double choose_cpu_ms{};
    double map_cpu_ms{};
    double fastd_cpu_ms{};
    std::uint64_t packed_bytes{};
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x) {
            const auto moving=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>((x*3u+y*5u+moving*7u+fi*2u)&255u);
        }
    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((80u+x+y+fi)&255u);
            b[ys+us+i]=static_cast<Byte>((170u+2u*x+y+fi*2u)&255u);
        }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2,ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2,tch=t.height/2;
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

template<class Fn>
static void parallel_for(std::size_t n,std::uint32_t workers,Fn fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for(std::uint32_t w=0;w<workers;++w)
        pool.emplace_back([&,w]{
            for(;;) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=n) break;
                fn(i,w);
            }
        });
    for(auto& t:pool) t.join();
}

static double percentile(std::vector<double> v,double q) {
    std::sort(v.begin(),v.end());
    const double pos=q*static_cast<double>(v.size()-1);
    const auto lo=static_cast<std::size_t>(std::floor(pos));
    const auto hi=static_cast<std::size_t>(std::ceil(pos));
    if(lo==hi) return v[lo];
    return v[lo]+(v[hi]-v[lo])*(pos-lo);
}

static void print_metric(const char* name,const std::vector<double>& v) {
    const double mean=std::accumulate(v.begin(),v.end(),0.0)/v.size();
    std::cout<<"STABLE_STAGE_METRIC stage="<<name
             <<" mean_ms="<<mean
             <<" median_ms="<<percentile(v,0.5)
             <<" p95_ms="<<percentile(v,0.95)
             <<"\n";
}

int main() {
    try {
        constexpr std::uint32_t fw=3840,fh=2160,workers=4,warmup=2,measured=12;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
        std::vector<AuroraKhepriFastDMemoryAdapter> encBackend(workers),decBackend(workers);

        std::vector<FrameStats> measuredStats;
        auto prev=make_frame(fw,fh,0);

        for(std::uint32_t fi=1;fi<=warmup+measured;++fi) {
            const auto cur=make_frame(fw,fh,fi);
            std::vector<EncodedTile> encoded(plan.tiles.size());
            std::vector<StageStats> workersStats(workers);

            const auto wall0=Clock::now();
            parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
                const auto& t=plan.tiles[i];
                const auto a=Clock::now();
                auto c=extract_tile(cur,fw,fh,t);
                auto p=extract_tile(prev,fw,fh,t);
                const auto b=Clock::now();
                auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
                const auto d=Clock::now();
                const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
                const auto e=Clock::now();
                auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
                const auto f=Clock::now();
                auto packed=encBackend[worker].encode(mapped);
                const auto g=Clock::now();

                auto& s=workersStats[worker];
                s.extract+=std::chrono::duration<double,std::milli>(b-a).count();
                s.motion+=std::chrono::duration<double,std::milli>(d-b).count();
                s.choose+=std::chrono::duration<double,std::milli>(e-d).count();
                s.map+=std::chrono::duration<double,std::milli>(f-e).count();
                s.fastd+=std::chrono::duration<double,std::milli>(g-f).count();
                encoded[i]=EncodedTile{t,std::move(mr.motion_map),mode,std::move(packed)};
            });
            const auto wall1=Clock::now();

            std::vector<Bytes> decoded(encoded.size());
            parallel_for(encoded.size(),workers,[&](std::size_t i,std::uint32_t worker){
                const auto& et=encoded[i];
                auto p=extract_tile(prev,fw,fh,et.tile);
                auto mapped=decBackend[worker].decode(et.packed);
                auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
                decoded[i]=AuroraVideoMotion::decode_mc8r4(et.motion,residual,p,et.tile.width,et.tile.height);
            });

            std::uint64_t bytes=0;
            for(std::size_t i=0;i<encoded.size();++i) {
                if(decoded[i]!=extract_tile(cur,fw,fh,encoded[i].tile))
                    throw std::runtime_error("stable stage roundtrip mismatch");
                bytes+=encoded[i].packed.size()+encoded[i].motion.size()+2;
            }

            if(fi>warmup) {
                FrameStats fs;
                fs.wall_ms=std::chrono::duration<double,std::milli>(wall1-wall0).count();
                fs.packed_bytes=bytes;
                for(const auto& s:workersStats) {
                    fs.extract_cpu_ms+=s.extract;
                    fs.motion_cpu_ms+=s.motion;
                    fs.choose_cpu_ms+=s.choose;
                    fs.map_cpu_ms+=s.map;
                    fs.fastd_cpu_ms+=s.fastd;
                }
                measuredStats.push_back(fs);
                std::cout<<"STABLE_STAGE_FRAME frame="<<(fi-warmup)
                         <<" wall_ms="<<fs.wall_ms
                         <<" extract_cpu_ms="<<fs.extract_cpu_ms
                         <<" motion_cpu_ms="<<fs.motion_cpu_ms
                         <<" choose_cpu_ms="<<fs.choose_cpu_ms
                         <<" map_cpu_ms="<<fs.map_cpu_ms
                         <<" fastd_cpu_ms="<<fs.fastd_cpu_ms
                         <<" packed_bytes="<<bytes
                         <<" lossless=1\n";
            }
            prev=cur;
        }

        std::vector<double> wall,extract,motion,choose,map,fastd;
        std::uint64_t totalBytes=0;
        for(const auto& s:measuredStats) {
            wall.push_back(s.wall_ms);
            extract.push_back(s.extract_cpu_ms);
            motion.push_back(s.motion_cpu_ms);
            choose.push_back(s.choose_cpu_ms);
            map.push_back(s.map_cpu_ms);
            fastd.push_back(s.fastd_cpu_ms);
            totalBytes+=s.packed_bytes;
        }

        std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";
        print_metric("wall",wall);
        print_metric("extract_cpu",extract);
        print_metric("motion_cpu",motion);
        print_metric("choose_cpu",choose);
        print_metric("map_cpu",map);
        print_metric("fastd_cpu",fastd);

        const double medWall=percentile(wall,0.5);
        const double medCpu=percentile(extract,0.5)+percentile(motion,0.5)+percentile(choose,0.5)+percentile(map,0.5)+percentile(fastd,0.5);
        std::cout<<"STABLE_STAGE_PASS frames="<<measuredStats.size()
                 <<" wall_median_ms="<<medWall
                 <<" wall_p95_ms="<<percentile(wall,0.95)
                 <<" median_fps="<<(1000.0/medWall)
                 <<" median_cpu_sum_ms="<<medCpu
                 <<" mean_packed_bytes="<<(static_cast<double>(totalBytes)/measuredStats.size())
                 <<" lossless=1\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
