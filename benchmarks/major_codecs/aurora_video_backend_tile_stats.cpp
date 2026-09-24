#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#if defined(AURORA_USE_FASTD)
#include "AuroraKhepriFastDMemoryAdapter.h"
using Backend=aurora::media::AuroraKhepriFastDMemoryAdapter;
static constexpr const char* kBackendName="FASTD";
#else
#include "AuroraKhepriExp37MemoryAdapter.h"
using Backend=aurora::media::AuroraKhepriExp37MemoryAdapter;
static constexpr const char* kBackendName="EXP37";
#endif
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x) {
            const auto moving=((x+fi*5u)/48u + (y+fi*3u)/40u) & 15u;
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+moving*7u+fi*2u)&255u);
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

static void run_case(const char* name,std::uint32_t fw,std::uint32_t fh) {
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,
                                         cfg.tile_halo,cfg.max_concurrent_tiles);
    const auto prev=make_frame(fw,fh,0);
    const auto cur=make_frame(fw,fh,1);
    Backend backend;

    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        auto c=extract_tile(cur,fw,fh,tile);
        auto p=extract_tile(prev,fw,fh,tile);
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,tile.width,tile.height,4.0,9);
        const double mean=AuroraVideoResidual::mean_signed_magnitude(mr.residual_yuv420);
        std::uint64_t zeros=0;
        for(const auto b:mr.residual_yuv420) if(b==0) ++zeros;
        const double zero_pct=mr.residual_yuv420.empty()?0.0:
            100.0*static_cast<double>(zeros)/mr.residual_yuv420.size();
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);

        const auto t0=Clock::now();
        auto packed=backend.encode(mapped);
        const auto t1=Clock::now();
        auto decoded=backend.decode(packed);
        if(decoded!=mapped) throw std::runtime_error("backend roundtrip mismatch");

        const double us=std::chrono::duration<double,std::micro>(t1-t0).count();
        std::cout<<"TILE_STAT"
                 <<" backend="<<kBackendName
                 <<" name="<<name
                 <<" tile="<<i
                 <<" mean="<<mean
                 <<" zero_pct="<<zero_pct
                 <<" encode_us="<<us
                 <<" packed="<<packed.size()
                 <<" raw="<<mapped.size()
                 <<"\n";
    }
}

int main() {
    try {
        run_case("1080p",1920,1080);
        run_case("1440p",2560,1440);
        run_case("4K",3840,2160);
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
