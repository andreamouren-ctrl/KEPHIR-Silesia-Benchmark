#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#define main aurora_kephir_exp41_cli_main
#include "../../KEPHIR_2_EXP41_PROFILE.cpp"
#undef main
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

using namespace aurora::media;

namespace {

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

void extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,
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

std::vector<Bytes> build_corpus() {
    constexpr std::uint32_t w=3840,h=2160;
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(
        w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    const auto prev=make_frame(w,h,0);
    const auto cur=make_frame(w,h,1);

    std::vector<Bytes> mapped;
    mapped.reserve(plan.tiles.size());
    Bytes ct,pt;
    for(const auto& tile:plan.tiles) {
        extract_tile(cur,w,h,tile,ct);
        extract_tile(prev,w,h,tile,pt);
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
            ct,pt,tile.width,tile.height,4.0,9);
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        mapped.push_back(AuroraVideoResidual::map(mr.residual_yuv420,mode));
    }
    return mapped;
}

} // namespace

int main() {
    try {
        const auto corpus=build_corpus();
        k2_exp41_reset_profile();

        std::uint64_t input_bytes=0;
        std::uint64_t packed_bytes=0;

        for(const auto& mapped:corpus) {
            input_bytes+=mapped.size();
            std::vector<std::uint8_t> d(mapped.begin(),mapped.end());
            const double localDpen=k2_adaptive_dpen(d,1.20,K2_ADAPT_MODE);
            const auto ts=parse(d,6.55,9.42,localDpen);
            const auto encoded=::encode(d,ts);
            const auto decoded=::decode(encoded,d.size());
            if(decoded!=d)
                throw std::runtime_error("EXP41 profile roundtrip mismatch");
            packed_bytes+=encoded.size();
        }

        const auto& p=k2_exp41_profile;
        const double reuse_pct=p.findpred_nodes
            ? 100.0*static_cast<double>(p.shared_cache_hits)/
              static_cast<double>(p.findpred_nodes)
            : 0.0;
        const double pred_compute_pct=p.findpred_nodes
            ? 100.0*static_cast<double>(p.predictive_match_computes)/
              static_cast<double>(p.findpred_nodes)
            : 0.0;
        const double early_stop_pct=p.findbest_calls
            ? 100.0*static_cast<double>(p.findbest_early_stops)/
              static_cast<double>(p.findbest_calls)
            : 0.0;

        std::cout<<"AURORA_EXP41_PARSER_PROFILE_PASS"
                 <<" tiles="<<corpus.size()
                 <<" input_bytes="<<input_bytes
                 <<" packed_bytes="<<packed_bytes
                 <<" findbest_calls="<<p.findbest_calls
                 <<" findpred_calls="<<p.findpred_calls
                 <<" findbest_nodes="<<p.findbest_nodes
                 <<" findpred_nodes="<<p.findpred_nodes
                 <<" findbest_early_stops="<<p.findbest_early_stops
                 <<" shared_cache_hits="<<p.shared_cache_hits
                 <<" shared_cache_misses="<<p.shared_cache_misses
                 <<" predictive_match_computes="<<p.predictive_match_computes
                 <<" predictive_scored_candidates="<<p.predictive_scored_candidates
                 <<" cache_reuse_pct="<<reuse_pct
                 <<" predictive_compute_pct="<<pred_compute_pct
                 <<" findbest_early_stop_pct="<<early_stop_pct
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
