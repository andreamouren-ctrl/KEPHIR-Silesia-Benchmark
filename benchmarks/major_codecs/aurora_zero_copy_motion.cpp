#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
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

struct Encoded {
    Bytes motion;
    Bytes residual;
};

Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t phase) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            out[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+phase*2u+((x/64u+phase)%7u)*3u+
                 ((y/48u+phase)%5u)*2u)&255u);
    for(std::uint32_t y=0;y<h/2;++y)
        for(std::uint32_t x=0;x<w/2;++x) {
            const auto i=static_cast<std::size_t>(y)*(w/2)+x;
            out[ys+i]=static_cast<Byte>((96u+x+y+phase)&255u);
            out[ys+us+i]=static_cast<Byte>((160u+2u*x+y+phase*2u)&255u);
        }
    return out;
}

void extract_region_into(ByteView frame,
                         std::uint32_t fw,std::uint32_t fh,
                         const VideoTile& t,Bytes& out) {
    const std::size_t fys=static_cast<std::size_t>(fw)*fh;
    const std::size_t fus=static_cast<std::size_t>(fw/2)*(fh/2);
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const std::size_t tus=static_cast<std::size_t>(t.width/2)*(t.height/2);
    const auto fcw=fw/2;
    const auto tcw=t.width/2;

    out.resize(tys+2*tus);
    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    out.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<t.height/2;++y) {
        const auto src=static_cast<std::size_t>(t.y/2+y)*fcw+t.x/2;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(fys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(fys+fus+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
}

std::uint64_t fnv1a(ByteView bytes,std::uint64_t h=1469598103934665603ull) {
    for(const auto b:bytes) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

std::uint64_t fingerprint(const std::vector<Encoded>& encoded) {
    std::uint64_t h=1469598103934665603ull;
    for(const auto& e:encoded) {
        h=fnv1a(e.motion,h);
        h=fnv1a(e.residual,h);
    }
    return h;
}

double legacy_encode(ByteView cur,ByteView prev,const VideoTilePlan& plan,
                     std::vector<Encoded>& encoded) {
    Bytes ct,pt;
    const auto t0=Clock::now();
    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        extract_region_into(cur,plan.frame_width,plan.frame_height,tile,ct);
        extract_region_into(prev,plan.frame_width,plan.frame_height,tile,pt);
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
            ct,pt,tile.width,tile.height,4.0,9);
        encoded[i]={std::move(mr.motion_map),std::move(mr.residual_yuv420)};
    }
    return std::chrono::duration<double>(Clock::now()-t0).count();
}

double zero_copy_encode(ByteView cur,ByteView prev,const VideoTilePlan& plan,
                        std::vector<Encoded>& encoded) {
    const auto t0=Clock::now();
    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        auto mr=AuroraVideoMotion::encode_mc8r4_region_adaptive(
            cur,prev,plan.frame_width,plan.frame_height,
            tile.x,tile.y,tile.width,tile.height,4.0,9);
        encoded[i]={std::move(mr.motion_map),std::move(mr.residual_yuv420)};
    }
    return std::chrono::duration<double>(Clock::now()-t0).count();
}

double legacy_decode(ByteView prev,const VideoTilePlan& plan,
                     const std::vector<Encoded>& encoded,std::uint64_t& hash) {
    Bytes pt;
    hash=1469598103934665603ull;
    const auto t0=Clock::now();
    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        extract_region_into(prev,plan.frame_width,plan.frame_height,tile,pt);
        auto dec=AuroraVideoMotion::decode_mc8r4(
            encoded[i].motion,encoded[i].residual,pt,tile.width,tile.height);
        hash=fnv1a(dec,hash);
    }
    return std::chrono::duration<double>(Clock::now()-t0).count();
}

double zero_copy_decode(ByteView prev,const VideoTilePlan& plan,
                        const std::vector<Encoded>& encoded,std::uint64_t& hash) {
    hash=1469598103934665603ull;
    const auto t0=Clock::now();
    for(std::size_t i=0;i<plan.tiles.size();++i) {
        const auto& tile=plan.tiles[i];
        auto dec=AuroraVideoMotion::decode_mc8r4_region(
            encoded[i].motion,encoded[i].residual,prev,
            plan.frame_width,plan.frame_height,
            tile.x,tile.y,tile.width,tile.height);
        hash=fnv1a(dec,hash);
    }
    return std::chrono::duration<double>(Clock::now()-t0).count();
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t fw=3840,fh=2160;
        constexpr int loops=6;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(
            fw,fh,cfg.tile_width,cfg.tile_height,
            cfg.tile_halo,cfg.max_concurrent_tiles);
        const auto prev=make_frame(fw,fh,0);
        const auto cur=make_frame(fw,fh,1);

        std::vector<Encoded> legacy(plan.tiles.size()),direct(plan.tiles.size());

        // Warm-up plus an explicit output-equivalence gate.
        (void)legacy_encode(cur,prev,plan,legacy);
        (void)zero_copy_encode(cur,prev,plan,direct);
        if(fingerprint(legacy)!=fingerprint(direct))
            throw std::runtime_error("encode output mismatch");

        std::uint64_t legacy_dec_hash=0,direct_dec_hash=0;
        (void)legacy_decode(prev,plan,legacy,legacy_dec_hash);
        (void)zero_copy_decode(prev,plan,direct,direct_dec_hash);
        if(legacy_dec_hash!=direct_dec_hash)
            throw std::runtime_error("decode output mismatch");

        double legacy_enc=0.0,direct_enc=0.0;
        double legacy_dec=0.0,direct_dec=0.0;
        for(int i=0;i<loops;++i) {
            legacy_enc+=legacy_encode(cur,prev,plan,legacy);
            direct_enc+=zero_copy_encode(cur,prev,plan,direct);

            std::uint64_t h1=0,h2=0;
            legacy_dec+=legacy_decode(prev,plan,legacy,h1);
            direct_dec+=zero_copy_decode(prev,plan,direct,h2);
            if(h1!=h2) throw std::runtime_error("decode hash changed during benchmark");
        }

        legacy_enc/=loops;
        direct_enc/=loops;
        legacy_dec/=loops;
        direct_dec/=loops;

        const std::uint64_t frame_bytes=
            static_cast<std::uint64_t>(fw)*fh*3ull/2ull;
        const std::uint64_t avoided_encode_copy=frame_bytes*2ull;
        const std::uint64_t avoided_decode_copy=frame_bytes;
        const std::uint64_t avoided_total=avoided_encode_copy+avoided_decode_copy;

        std::cout<<"AURORA_ZERO_COPY_MOTION_BENCH"
                 <<" tiles="<<plan.tiles.size()
                 <<" legacy_encode_ms="<<(legacy_enc*1000.0)
                 <<" zero_encode_ms="<<(direct_enc*1000.0)
                 <<" encode_speedup_x="<<(legacy_enc/direct_enc)
                 <<" legacy_decode_ms="<<(legacy_dec*1000.0)
                 <<" zero_decode_ms="<<(direct_dec*1000.0)
                 <<" decode_speedup_x="<<(legacy_dec/direct_dec)
                 <<" legacy_total_ms="<<((legacy_enc+legacy_dec)*1000.0)
                 <<" zero_total_ms="<<((direct_enc+direct_dec)*1000.0)
                 <<" total_speedup_x="<<((legacy_enc+legacy_dec)/(direct_enc+direct_dec))
                 <<" avoided_copy_bytes_per_frame="<<avoided_total
                 <<" fingerprint="<<fingerprint(direct)
                 <<"\n";
        std::cout<<"AURORA_ZERO_COPY_MOTION_BENCH_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
