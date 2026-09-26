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

namespace {

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    Bytes packed;
};

struct StageTotals {
    double extract_encode{};
    double motion_encode{};
    double residual_map{};
    double khepri_encode{};
    double extract_decode{};
    double khepri_decode{};
    double residual_unmap{};
    double motion_decode{};
    double paste{};
};

Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t frame_idx) {
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

void extract_tile_into(ByteView frame,std::uint32_t fw,std::uint32_t fh,
                       const VideoTile& t,Bytes& out) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2, ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2, tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    (void)ch;

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

void paste_tile(Bytes& frame,std::uint32_t fw,std::uint32_t fh,
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
double timed(Fn&& fn) {
    const auto t0=Clock::now();
    fn();
    return std::chrono::duration<double>(Clock::now()-t0).count();
}

struct RunResult {
    StageTotals stages;
    std::uint64_t packed_bytes{};
};

RunResult run_once(ByteView cur,ByteView prev,const VideoTilePlan& plan) {
    std::vector<EncodedTile> encoded(plan.tiles.size());
    std::vector<Bytes> decoded(plan.tiles.size());
    AuroraKhepriExp37MemoryAdapter khepri;
    Bytes current_tile;
    Bytes previous_tile;

    const auto max_tile_bytes=
        static_cast<std::size_t>(plan.tile_width)*plan.tile_height*3/2;
    current_tile.reserve(max_tile_bytes);
    previous_tile.reserve(max_tile_bytes);

    StageTotals s;

    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        s.extract_encode += timed([&]{
            extract_tile_into(cur,plan.frame_width,plan.frame_height,tile,current_tile);
            extract_tile_into(prev,plan.frame_width,plan.frame_height,tile,previous_tile);
        });

        MotionResidual mr;
        s.motion_encode += timed([&]{
            mr=AuroraVideoMotion::encode_mc8r4_adaptive(
                current_tile,previous_tile,tile.width,tile.height,4.0,9);
        });

        VideoResidualMode mode{};
        Bytes mapped;
        s.residual_map += timed([&]{
            mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        });

        Bytes packed;
        s.khepri_encode += timed([&]{
            packed=khepri.encode(mapped);
        });

        encoded[i]=EncodedTile{
            tile,std::move(mr.motion_map),mode,std::move(packed)
        };
    }

    for(std::size_t i=0;i<encoded.size();++i) {
        const auto& et=encoded[i];
        s.extract_decode += timed([&]{
            extract_tile_into(
                prev,plan.frame_width,plan.frame_height,et.tile,previous_tile);
        });

        Bytes mapped;
        s.khepri_decode += timed([&]{
            mapped=khepri.decode(et.packed);
        });

        Bytes residual;
        s.residual_unmap += timed([&]{
            residual=AuroraVideoResidual::unmap(mapped,et.mode);
        });

        s.motion_decode += timed([&]{
            decoded[i]=AuroraVideoMotion::decode_mc8r4(
                et.motion,residual,previous_tile,et.tile.width,et.tile.height);
        });
    }

    Bytes recon(static_cast<std::size_t>(plan.frame_width)*plan.frame_height*3/2);
    s.paste += timed([&]{
        for(std::size_t i=0;i<decoded.size();++i)
            paste_tile(
                recon,plan.frame_width,plan.frame_height,plan.tiles[i],decoded[i]);
    });

    if(!std::equal(recon.begin(),recon.end(),cur.begin(),cur.end()))
        throw std::runtime_error("4K profiler reconstruction mismatch");

    std::uint64_t packed_bytes=0;
    for(const auto& e:encoded)
        packed_bytes+=e.packed.size()+e.motion.size()+1;

    return RunResult{s,packed_bytes};
}

void add(StageTotals& a,const StageTotals& b) {
    a.extract_encode+=b.extract_encode;
    a.motion_encode+=b.motion_encode;
    a.residual_map+=b.residual_map;
    a.khepri_encode+=b.khepri_encode;
    a.extract_decode+=b.extract_decode;
    a.khepri_decode+=b.khepri_decode;
    a.residual_unmap+=b.residual_unmap;
    a.motion_decode+=b.motion_decode;
    a.paste+=b.paste;
}

void divide(StageTotals& s,double n) {
    s.extract_encode/=n;
    s.motion_encode/=n;
    s.residual_map/=n;
    s.khepri_encode/=n;
    s.extract_decode/=n;
    s.khepri_decode/=n;
    s.residual_unmap/=n;
    s.motion_decode/=n;
    s.paste/=n;
}

void print_stage(const char* name,double seconds,double total) {
    std::cout<<"STAGE"
             <<" name="<<name
             <<" ms="<<(seconds*1000.0)
             <<" percent="<<(total>0.0 ? 100.0*seconds/total : 0.0)
             <<"\n";
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        constexpr int loops=3;

        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(
            w,h,cfg.tile_width,cfg.tile_height,
            cfg.tile_halo,cfg.max_concurrent_tiles);
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,1);

        // Warm-up.
        (void)run_once(cur,prev,plan);

        StageTotals avg{};
        std::uint64_t payload=0;
        for(int i=0;i<loops;++i) {
            auto r=run_once(cur,prev,plan);
            add(avg,r.stages);
            payload=r.packed_bytes;
        }
        divide(avg,loops);

        const double encode=
            avg.extract_encode+avg.motion_encode+avg.residual_map+avg.khepri_encode;
        const double decode=
            avg.extract_decode+avg.khepri_decode+avg.residual_unmap+
            avg.motion_decode+avg.paste;
        const double total=encode+decode;

        std::cout<<"AURORA_4K_STAGE_PROFILE"
                 <<" tiles="<<plan.tiles.size()
                 <<" encode_ms="<<(encode*1000.0)
                 <<" encode_fps="<<(1.0/encode)
                 <<" decode_ms="<<(decode*1000.0)
                 <<" decode_fps="<<(1.0/decode)
                 <<" total_ms="<<(total*1000.0)
                 <<" total_fps="<<(1.0/total)
                 <<" packed_bytes="<<payload
                 <<"\n";

        print_stage("encode_extract",avg.extract_encode,encode);
        print_stage("encode_motion",avg.motion_encode,encode);
        print_stage("encode_residual_map",avg.residual_map,encode);
        print_stage("encode_khepri",avg.khepri_encode,encode);

        print_stage("decode_extract",avg.extract_decode,decode);
        print_stage("decode_khepri",avg.khepri_decode,decode);
        print_stage("decode_residual_unmap",avg.residual_unmap,decode);
        print_stage("decode_motion",avg.motion_decode,decode);
        print_stage("decode_paste",avg.paste,decode);

        std::cout<<"AURORA_4K_STAGE_PROFILE_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
