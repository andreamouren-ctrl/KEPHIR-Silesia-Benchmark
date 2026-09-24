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

#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#define main aurora_fastd_profile_cli_main
#include "../../KEPHIR_SPEED_D_SOURCE.cpp"
#undef main
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

namespace {
constexpr double kLit=6.55;
constexpr double kMc=9.42;
constexpr double kDpen=1.20;

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    std::vector<std::uint8_t> payload;
    std::size_t raw_size{};
    bool raw{};
};

struct WorkerStats {
    double prep{};
    double dpen{};
    double parse{};
    double entropy{};
};

struct FrameStats {
    double wall_ms{};
    double prep_cpu_ms{};
    double dpen_cpu_ms{};
    double parse_cpu_ms{};
    double entropy_cpu_ms{};
    std::uint64_t packed_bytes{};
};

Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi) {
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

Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
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
void parallel_for(std::size_t n,std::uint32_t workers,Fn fn) {
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

double percentile(std::vector<double> v,double q) {
    std::sort(v.begin(),v.end());
    const double pos=q*static_cast<double>(v.size()-1);
    const auto lo=static_cast<std::size_t>(std::floor(pos));
    const auto hi=static_cast<std::size_t>(std::ceil(pos));
    if(lo==hi) return v[lo];
    return v[lo]+(v[hi]-v[lo])*(pos-lo);
}

void metric(const char* name,const std::vector<double>& v) {
    const double mean=std::accumulate(v.begin(),v.end(),0.0)/v.size();
    std::cout<<"FASTD_INTERNAL_METRIC stage="<<name
             <<" mean_ms="<<mean
             <<" median_ms="<<percentile(v,0.5)
             <<" p95_ms="<<percentile(v,0.95)
             <<"\n";
}
} // namespace

int main() {
    try {
        constexpr std::uint32_t fw=3840,fh=2160,workers=4,warmup=2,measured=12;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
        std::vector<FrameStats> samples;
        auto prev=make_frame(fw,fh,0);

        for(std::uint32_t fi=1;fi<=warmup+measured;++fi) {
            const auto cur=make_frame(fw,fh,fi);
            std::vector<EncodedTile> encoded(plan.tiles.size());
            std::vector<WorkerStats> ws(workers);

            const auto wall0=Clock::now();
            parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
                const auto& t=plan.tiles[i];
                auto c=extract_tile(cur,fw,fh,t);
                auto p=extract_tile(prev,fw,fh,t);
                auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
                const auto rmode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
                auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,rmode);

                const auto a=Clock::now();
                std::vector<std::uint8_t> d(mapped.begin(),mapped.end());
                const auto b=Clock::now();
                const double localDpen=k2_adaptive_dpen(d,kDpen,K2_ADAPT_MODE);
                const auto c0=Clock::now();
                const auto ts=parse(d,kLit,kMc,localDpen);
                const auto d0=Clock::now();
                auto payload=::encode(d,ts);
                const auto e0=Clock::now();

                bool raw=false;
                if(payload.size()>=d.size()) {
                    payload=d;
                    raw=true;
                }

                auto& s=ws[worker];
                s.prep+=std::chrono::duration<double,std::milli>(b-a).count();
                s.dpen+=std::chrono::duration<double,std::milli>(c0-b).count();
                s.parse+=std::chrono::duration<double,std::milli>(d0-c0).count();
                s.entropy+=std::chrono::duration<double,std::milli>(e0-d0).count();

                encoded[i]=EncodedTile{t,std::move(mr.motion_map),rmode,std::move(payload),d.size(),raw};
            });
            const auto wall1=Clock::now();

            parallel_for(encoded.size(),workers,[&](std::size_t i,std::uint32_t){
                const auto& et=encoded[i];
                std::vector<std::uint8_t> mapped;
                if(et.raw) mapped=et.payload;
                else mapped=::decode(et.payload,et.raw_size);
                auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
                auto p=extract_tile(prev,fw,fh,et.tile);
                auto out=AuroraVideoMotion::decode_mc8r4(et.motion,residual,p,et.tile.width,et.tile.height);
                if(out!=extract_tile(cur,fw,fh,et.tile))
                    throw std::runtime_error("FAST-D internal profile roundtrip mismatch");
            });

            if(fi>warmup) {
                FrameStats fs;
                fs.wall_ms=std::chrono::duration<double,std::milli>(wall1-wall0).count();
                for(const auto& s:ws) {
                    fs.prep_cpu_ms+=s.prep;
                    fs.dpen_cpu_ms+=s.dpen;
                    fs.parse_cpu_ms+=s.parse;
                    fs.entropy_cpu_ms+=s.entropy;
                }
                for(const auto& e:encoded)
                    fs.packed_bytes+=e.payload.size()+e.motion.size()+17;
                samples.push_back(fs);
                std::cout<<"FASTD_INTERNAL_FRAME frame="<<(fi-warmup)
                         <<" wall_ms="<<fs.wall_ms
                         <<" prep_cpu_ms="<<fs.prep_cpu_ms
                         <<" dpen_cpu_ms="<<fs.dpen_cpu_ms
                         <<" parse_cpu_ms="<<fs.parse_cpu_ms
                         <<" entropy_cpu_ms="<<fs.entropy_cpu_ms
                         <<" packed_bytes="<<fs.packed_bytes
                         <<" lossless=1\n";
            }
            prev=cur;
        }

        std::vector<double> wall,prep,dpen,parsev,entropy;
        std::uint64_t totalBytes=0;
        for(const auto& s:samples) {
            wall.push_back(s.wall_ms);
            prep.push_back(s.prep_cpu_ms);
            dpen.push_back(s.dpen_cpu_ms);
            parsev.push_back(s.parse_cpu_ms);
            entropy.push_back(s.entropy_cpu_ms);
            totalBytes+=s.packed_bytes;
        }

        std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";
        metric("wall",wall);
        metric("prep_cpu",prep);
        metric("dpen_cpu",dpen);
        metric("parse_cpu",parsev);
        metric("entropy_cpu",entropy);

        const double mp=percentile(prep,0.5),md=percentile(dpen,0.5),mparse=percentile(parsev,0.5),me=percentile(entropy,0.5);
        const double internal=mp+md+mparse+me;
        std::cout<<"FASTD_INTERNAL_PASS frames="<<samples.size()
                 <<" wall_median_ms="<<percentile(wall,0.5)
                 <<" wall_p95_ms="<<percentile(wall,0.95)
                 <<" prep_median_pct="<<(100.0*mp/internal)
                 <<" dpen_median_pct="<<(100.0*md/internal)
                 <<" parse_median_pct="<<(100.0*mparse/internal)
                 <<" entropy_median_pct="<<(100.0*me/internal)
                 <<" mean_packed_bytes="<<(static_cast<double>(totalBytes)/samples.size())
                 <<" lossless=1\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
