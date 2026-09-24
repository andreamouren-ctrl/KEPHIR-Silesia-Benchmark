#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct Metrics {
    std::uint64_t raw_bytes{};
    std::uint64_t packed_bytes{};
    std::uint64_t motion_bytes{};
    double encode_seconds{};
    double decode_seconds{};
};

struct Resolution {
    const char* name;
    std::uint32_t width;
    std::uint32_t height;
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=0;x<w;++x) {
            const auto moving=((x+frame_idx*5u)/48u + (y+frame_idx*3u)/40u) & 15u;
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+moving*7u+frame_idx*2u)&255u);
        }
    }
    const auto cw=w/2, ch=h/2;
    for(std::uint32_t y=0;y<ch;++y) {
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((80u+x+y+frame_idx)&255u);
            b[ys+us+i]=static_cast<Byte>((170u+2u*x+y+frame_idx*2u)&255u);
        }
    }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    (void)fh;
    const std::size_t ys=static_cast<std::size_t>(fw)*t.y + 0; // only to keep arithmetic explicit
    (void)ys;
    const std::size_t frame_ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2;
    const std::size_t frame_us=static_cast<std::size_t>(cw)*(fh/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2;
    const std::uint32_t tch=t.height/2;
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
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(frame_ys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(frame_ys+frame_us+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
    return out;
}

static void paste_tile(Bytes& frame,std::uint32_t fw,std::uint32_t fh,
                       const VideoTile& t,ByteView tile) {
    const std::size_t frame_ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2;
    const std::size_t frame_us=static_cast<std::size_t>(cw)*(fh/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2;
    const std::uint32_t tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;

    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(y)*t.width;
        const auto dst=static_cast<std::size_t>(t.y+y)*fw+t.x;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    frame.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(y)*tcw;
        const auto dst=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(frame_ys+dst));
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+tus+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(frame_ys+frame_us+dst));
    }
}

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode;
    Bytes packed;
};

static void run_resolution(const Resolution& r,AuroraKhepriExp37MemoryAdapter& khepri) {
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(r.width,r.height,cfg.tile_width,cfg.tile_height,
                                         cfg.tile_halo,cfg.max_concurrent_tiles);

    const auto prev=make_frame(r.width,r.height,0);
    const auto cur=make_frame(r.width,r.height,1);
    Metrics m;
    std::vector<EncodedTile> encoded;
    encoded.reserve(plan.tiles.size());

    const auto wall0=Clock::now();
    for(const auto& tile:plan.tiles) {
        auto c=extract_tile(cur,r.width,r.height,tile);
        auto p=extract_tile(prev,r.width,r.height,tile);
        const auto t0=Clock::now();
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,tile.width,tile.height,4.0,9);
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        auto packed=khepri.encode(mapped);
        const auto t1=Clock::now();

        m.encode_seconds+=std::chrono::duration<double>(t1-t0).count();
        m.raw_bytes+=mr.residual_yuv420.size();
        m.motion_bytes+=mr.motion_map.size();
        m.packed_bytes+=packed.size()+mr.motion_map.size()+1;
        encoded.push_back(EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)});
    }

    Bytes reconstructed(static_cast<std::size_t>(r.width)*r.height*3/2);
    for(const auto& et:encoded) {
        auto p=extract_tile(prev,r.width,r.height,et.tile);
        const auto t0=Clock::now();
        auto mapped=khepri.decode(et.packed);
        auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
        auto tile=AuroraVideoMotion::decode_mc8r4(
            et.motion,residual,p,et.tile.width,et.tile.height);
        const auto t1=Clock::now();
        m.decode_seconds+=std::chrono::duration<double>(t1-t0).count();
        paste_tile(reconstructed,r.width,r.height,et.tile,tile);
    }
    const auto wall1=Clock::now();
    if(reconstructed!=cur)
        throw std::runtime_error(std::string("roundtrip mismatch at ")+r.name);

    const double wall_ms=std::chrono::duration<double,std::milli>(wall1-wall0).count();
    const double fps=1000.0/wall_ms;
    const double enc_ms=m.encode_seconds*1000.0;
    const double dec_ms=m.decode_seconds*1000.0;
    const double enc_fps=1000.0/enc_ms;
    const double dec_fps=1000.0/dec_ms;
    const double mib=static_cast<double>(cur.size())/(1024.0*1024.0);
    const double mib_s=mib/(wall_ms/1000.0);
    const double ratio=100.0*static_cast<double>(m.packed_bytes)/m.raw_bytes;

    std::cout<<"MULTIRES_PASS"
             <<" name="<<r.name
             <<" width="<<r.width
             <<" height="<<r.height
             <<" tiles="<<plan.tiles.size()
             <<" frame_bytes="<<cur.size()
             <<" packed_bytes="<<m.packed_bytes
             <<" ratio_percent="<<ratio
             <<" wall_ms="<<wall_ms
             <<" wall_fps="<<fps
             <<" encode_ms="<<enc_ms
             <<" encode_fps="<<enc_fps
             <<" decode_ms="<<dec_ms
             <<" decode_fps="<<dec_fps
             <<" mib_s="<<mib_s
             <<" lossless=1"
             <<"\n";
}

int main() {
    try {
        const std::vector<Resolution> resolutions{
            {"480p",640,480},
            {"720p",1280,720},
            {"1080p",1920,1080},
            {"1440p",2560,1440},
            {"4K",3840,2160}
        };
        AuroraKhepriExp37MemoryAdapter khepri;
        for(const auto& r:resolutions) run_resolution(r,khepri);
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
