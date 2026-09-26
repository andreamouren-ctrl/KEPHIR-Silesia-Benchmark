#if defined(AURORA_KHEPRI_EXP38)
#include "AuroraKhepriExp38MemoryAdapter.h"
using Backend = aurora::media::AuroraKhepriExp38MemoryAdapter;
static constexpr const char* kBackendName = "EXP38_FUSED";
#else
#include "AuroraKhepriExp37MemoryAdapter.h"
using Backend = aurora::media::AuroraKhepriExp37MemoryAdapter;
static constexpr const char* kBackendName = "EXP37_DUAL";
#endif

#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

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

std::uint64_t fnv1a(ByteView data,std::uint64_t h=1469598103934665603ull) {
    for(const auto b:data) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

struct Corpus {
    std::vector<Bytes> mapped;
    std::uint64_t raw_bytes{};
    std::uint64_t fingerprint{};
};

Corpus build_corpus() {
    constexpr std::uint32_t w=3840,h=2160;
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(
        w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);

    const auto prev=make_frame(w,h,0);
    const auto cur=make_frame(w,h,1);

    Corpus corpus;
    corpus.mapped.reserve(plan.tiles.size());
    Bytes ct,pt;

    for(const auto& tile:plan.tiles) {
        extract_tile(cur,w,h,tile,ct);
        extract_tile(prev,w,h,tile,pt);
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
            ct,pt,tile.width,tile.height,4.0,9);
        const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
        corpus.raw_bytes+=mapped.size();
        corpus.fingerprint=fnv1a(mapped,corpus.fingerprint);
        corpus.mapped.push_back(std::move(mapped));
    }
    return corpus;
}

} // namespace

int main() {
    try {
        constexpr int loops=3;
        const auto corpus=build_corpus();
        Backend backend;

        std::vector<Bytes> encoded(corpus.mapped.size());

        // Warm-up plus exact decode validation.
        std::uint64_t warm_bytes=0;
        for(std::size_t i=0;i<corpus.mapped.size();++i) {
            encoded[i]=backend.encode(corpus.mapped[i]);
            warm_bytes+=encoded[i].size();
            const auto decoded=backend.decode(encoded[i]);
            if(decoded!=corpus.mapped[i])
                throw std::runtime_error("backend roundtrip mismatch");
        }

        double encode_s=0.0;
        double decode_s=0.0;
        std::uint64_t packed_bytes=0;
        std::uint64_t payload_fingerprint=0;

        for(int loop=0;loop<loops;++loop) {
            const auto e0=Clock::now();
            for(std::size_t i=0;i<corpus.mapped.size();++i)
                encoded[i]=backend.encode(corpus.mapped[i]);
            const auto e1=Clock::now();

            std::uint64_t this_bytes=0;
            std::uint64_t this_fp=1469598103934665603ull;
            for(const auto& x:encoded) {
                this_bytes+=x.size();
                this_fp=fnv1a(x,this_fp);
            }

            const auto d0=Clock::now();
            for(std::size_t i=0;i<corpus.mapped.size();++i) {
                const auto decoded=backend.decode(encoded[i]);
                if(decoded!=corpus.mapped[i])
                    throw std::runtime_error("timed backend roundtrip mismatch");
            }
            const auto d1=Clock::now();

            encode_s+=std::chrono::duration<double>(e1-e0).count();
            decode_s+=std::chrono::duration<double>(d1-d0).count();

            if(loop==0) {
                packed_bytes=this_bytes;
                payload_fingerprint=this_fp;
            } else if(this_bytes!=packed_bytes || this_fp!=payload_fingerprint) {
                throw std::runtime_error("non-deterministic backend output");
            }
        }

        encode_s/=loops;
        decode_s/=loops;

        std::cout<<"AURORA_KHEPRI_MEDIA_BACKEND_PASS"
                 <<" backend="<<kBackendName
                 <<" tiles="<<corpus.mapped.size()
                 <<" input_bytes="<<corpus.raw_bytes
                 <<" packed_bytes="<<packed_bytes
                 <<" ratio_percent="<<(100.0*packed_bytes/corpus.raw_bytes)
                 <<" encode_ms="<<(encode_s*1000.0)
                 <<" encode_fps="<<(1.0/encode_s)
                 <<" decode_ms="<<(decode_s*1000.0)
                 <<" decode_fps="<<(1.0/decode_s)
                 <<" input_fingerprint="<<corpus.fingerprint
                 <<" payload_fingerprint="<<payload_fingerprint
                 <<" warm_bytes="<<warm_bytes
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
