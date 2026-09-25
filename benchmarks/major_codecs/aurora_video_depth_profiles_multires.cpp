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
#include <cstdlib>
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
        pool.emplace_back([&,w] {
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

int main(int argc,char** argv) {
    try {
        if(argc!=4) throw std::runtime_error("usage: bench <profile-name> <width> <height>");
        const std::string profile=argv[1];
        const auto fw=static_cast<std::uint32_t>(std::stoul(argv[2]));
        const auto fh=static_cast<std::uint32_t>(std::stoul(argv[3]));
        if((fw&1u)||(fh&1u)) throw std::runtime_error("YUV420 requires even dimensions");

        constexpr std::uint32_t workers=4,warmup=2,measured=12;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
        std::vector<AuroraKhepriFastDMemoryAdapter> enc(workers),dec(workers);
        std::vector<double> wall;
        std::vector<std::uint64_t> bytes;
        auto prev=make_frame(fw,fh,0);

        for(std::uint32_t fi=1;fi<=warmup+measured;++fi) {
            const auto cur=make_frame(fw,fh,fi);
            std::vector<EncodedTile> out(plan.tiles.size());

            const auto t0=Clock::now();
            parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t w) {
                const auto& t=plan.tiles[i];
                auto c=extract_tile(cur,fw,fh,t);
                auto p=extract_tile(prev,fw,fh,t);
                auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
                const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
                auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
                out[i]=EncodedTile{t,std::move(mr.motion_map),mode,enc[w].encode(mapped)};
            });
            const auto t1=Clock::now();

            parallel_for(out.size(),workers,[&](std::size_t i,std::uint32_t w) {
                const auto& e=out[i];
                auto mapped=dec[w].decode(e.packed);
                auto residual=AuroraVideoResidual::unmap(mapped,e.mode);
                auto p=extract_tile(prev,fw,fh,e.tile);
                auto rec=AuroraVideoMotion::decode_mc8r4(e.motion,residual,p,e.tile.width,e.tile.height);
                if(rec!=extract_tile(cur,fw,fh,e.tile))
                    throw std::runtime_error("roundtrip mismatch");
            });

            if(fi>warmup) {
                std::uint64_t sz=0;
                for(const auto& e:out) sz+=e.packed.size()+e.motion.size()+2;
                const double ms=std::chrono::duration<double,std::milli>(t1-t0).count();
                wall.push_back(ms);
                bytes.push_back(sz);
                std::cout<<"DEPTH_MULTIRES_FRAME profile="<<profile
                         <<" width="<<fw<<" height="<<fh
                         <<" frame="<<(fi-warmup)
                         <<" encode_ms="<<ms
                         <<" packed_bytes="<<sz
                         <<" lossless=1\n";
            }
            prev=cur;
        }

        const double mean=std::accumulate(wall.begin(),wall.end(),0.0)/wall.size();
        const double med=percentile(wall,0.5);
        const double p95=percentile(wall,0.95);
        const double meanBytes=static_cast<double>(
            std::accumulate(bytes.begin(),bytes.end(),std::uint64_t{0}))/bytes.size();
        const double mbps30=meanBytes*8.0*30.0/1'000'000.0;
        const double mbps60=meanBytes*8.0*60.0/1'000'000.0;

        std::cout<<"DEPTH_MULTIRES_PASS profile="<<profile
                 <<" width="<<fw<<" height="<<fh
                 <<" frames="<<wall.size()
                 <<" mean_ms="<<mean
                 <<" median_ms="<<med
                 <<" p95_ms="<<p95
                 <<" median_fps="<<(1000.0/med)
                 <<" mean_packed_bytes="<<meanBytes
                 <<" bitrate30_mbps="<<mbps30
                 <<" bitrate60_mbps="<<mbps60
                 <<" lossless=1\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
