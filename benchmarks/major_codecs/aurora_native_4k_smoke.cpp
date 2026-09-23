#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoStreamScheduler.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct Metrics {
    std::uint64_t raw_bytes{};
    std::uint64_t packed_bytes{};
    std::uint64_t motion_bytes{};
    std::uint64_t tiles{};
    double encode_seconds{};
    double decode_seconds{};
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);

    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=0;x<w;++x) {
            const auto v=(x*3u+y*5u+frame_idx*2u+
                         ((x/64u+frame_idx)%7u)*3u+
                         ((y/48u+frame_idx)%5u)*2u) & 255u;
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(v);
        }
    }

    const auto cw=w/2;
    const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y) {
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((96u+x+y+frame_idx)&255u);
            b[ys+us+i]=static_cast<Byte>((160u+2u*x+y+frame_idx*2u)&255u);
        }
    }
    return b;
}

static Bytes extract_tile_yuv420(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    if((t.x%2)||(t.y%2)||(t.width%2)||(t.height%2))
        throw std::runtime_error("tile must be even-aligned for YUV420");
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2;
    const std::uint32_t ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;

    Bytes out(static_cast<std::size_t>(t.width)*t.height*3/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2;
    const std::uint32_t tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;

    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,out.begin()+static_cast<std::ptrdiff_t>(dst));
    }

    for(std::uint32_t y=0;y<tch;++y) {
        const auto sx=t.x/2;
        const auto sy=t.y/2+y;
        const auto src=static_cast<std::size_t>(sy)*cw+sx;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+us+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
    return out;
}

static void paste_tile_yuv420(Bytes& frame,std::uint32_t fw,std::uint32_t fh,
                              const VideoTile& t,ByteView tile) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const std::uint32_t cw=fw/2;
    const std::uint32_t ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;

    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::uint32_t tcw=t.width/2;
    const std::uint32_t tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;

    if(tile.size()!=tys+2*tus) throw std::runtime_error("tile size mismatch");

    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(y)*t.width;
        const auto dst=static_cast<std::size_t>(t.y+y)*fw+t.x;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    frame.begin()+static_cast<std::ptrdiff_t>(dst));
    }

    for(std::uint32_t y=0;y<tch;++y) {
        const auto sx=t.x/2;
        const auto sy=t.y/2+y;
        const auto dst=static_cast<std::size_t>(sy)*cw+sx;
        const auto src=static_cast<std::size_t>(y)*tcw;
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+dst));
        std::copy_n(tile.begin()+static_cast<std::ptrdiff_t>(tys+tus+src),tcw,
                    frame.begin()+static_cast<std::ptrdiff_t>(ys+us+dst));
    }
}

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    Bytes packed;
};

static std::vector<EncodedTile> encode_frame_tiles(ByteView cur,ByteView prev,
                                                   const VideoTilePlan& plan,
                                                   AuroraKhepriExp37MemoryAdapter& k,
                                                   Metrics& m) {
    std::vector<EncodedTile> out;
    out.reserve(plan.tiles.size());
    for(const auto& tile:plan.tiles) {
        auto c=extract_tile_yuv420(cur,plan.frame_width,plan.frame_height,tile);
        auto p=extract_tile_yuv420(prev,plan.frame_width,plan.frame_height,tile);

        const auto t0=Clock::now();
        auto mr=AuroraVideoMotion::encode_mc8r4(c,p,tile.width,tile.height);
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        auto packed=k.encode(mapped);
        const auto t1=Clock::now();

        m.encode_seconds+=std::chrono::duration<double>(t1-t0).count();
        m.raw_bytes+=mr.residual_yuv420.size();
        m.motion_bytes+=mr.motion_map.size();
        m.packed_bytes+=packed.size()+mr.motion_map.size()+1;
        ++m.tiles;

        out.push_back(EncodedTile{tile,std::move(mr.motion_map),mode,std::move(packed)});
    }
    return out;
}

static Bytes decode_frame_tiles(const std::vector<EncodedTile>& tiles,ByteView prev,
                                const VideoTilePlan& plan,
                                AuroraKhepriExp37MemoryAdapter& k,
                                Metrics& m) {
    Bytes frame(static_cast<std::size_t>(plan.frame_width)*plan.frame_height*3/2);
    for(const auto& et:tiles) {
        auto p=extract_tile_yuv420(prev,plan.frame_width,plan.frame_height,et.tile);

        const auto t0=Clock::now();
        auto mapped=k.decode(et.packed);
        auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
        auto tile=AuroraVideoMotion::decode_mc8r4(et.motion,residual,p,et.tile.width,et.tile.height);
        const auto t1=Clock::now();

        m.decode_seconds+=std::chrono::duration<double>(t1-t0).count();
        paste_tile_yuv420(frame,plan.frame_width,plan.frame_height,et.tile,tile);
    }
    return frame;
}

int main(int argc,char** argv) {
    try {
        std::uint32_t frames=3;
        if(argc>1) frames=static_cast<std::uint32_t>(std::stoul(argv[1]));
        if(frames<2 || frames>8) throw std::runtime_error("frames must be 2..8");

        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Streaming4K);
        const auto plan=make_video_tile_plan(w,h,cfg.tile_width,cfg.tile_height,
                                             cfg.tile_halo,cfg.max_concurrent_tiles);

        AuroraKhepriExp37MemoryAdapter khepri;
        Metrics m;

        auto prev=make_frame(w,h,0);
        const auto wall0=Clock::now();

        for(std::uint32_t fi=1;fi<frames;++fi) {
            auto cur=make_frame(w,h,fi);
            auto encoded=encode_frame_tiles(cur,prev,plan,khepri,m);
            auto reconstructed=decode_frame_tiles(encoded,prev,plan,khepri,m);
            if(reconstructed!=cur)
                throw std::runtime_error("4K native roundtrip mismatch at frame "+std::to_string(fi));
            prev=std::move(cur);
        }

        const auto wall1=Clock::now();
        const double wall=std::chrono::duration<double>(wall1-wall0).count();
        const auto processed=frames-1;
        const double fps=processed/wall;
        const double encfps=processed/m.encode_seconds;
        const double decfps=processed/m.decode_seconds;
        const double ratio=m.raw_bytes?100.0*static_cast<double>(m.packed_bytes)/m.raw_bytes:0.0;
        const double avg_ms=1000.0*wall/processed;

        std::cout<<"AURORA_NATIVE_4K_SMOKE_PASS\n";
        std::cout<<"frames_processed="<<processed<<"\n";
        std::cout<<"tiles_per_frame="<<plan.tiles.size()<<"\n";
        std::cout<<"wall_seconds="<<wall<<"\n";
        std::cout<<"wall_fps="<<fps<<"\n";
        std::cout<<"avg_frame_ms="<<avg_ms<<"\n";
        std::cout<<"encode_seconds="<<m.encode_seconds<<"\n";
        std::cout<<"encode_fps_serial="<<encfps<<"\n";
        std::cout<<"decode_seconds="<<m.decode_seconds<<"\n";
        std::cout<<"decode_fps_serial="<<decfps<<"\n";
        std::cout<<"residual_raw_bytes="<<m.raw_bytes<<"\n";
        std::cout<<"motion_bytes="<<m.motion_bytes<<"\n";
        std::cout<<"packed_plus_motion_bytes="<<m.packed_bytes<<"\n";
        std::cout<<"payload_ratio_percent="<<ratio<<"\n";
        std::cout<<"active_worker_estimated_bytes="<<plan.estimated_peak_parallel_bytes()<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
