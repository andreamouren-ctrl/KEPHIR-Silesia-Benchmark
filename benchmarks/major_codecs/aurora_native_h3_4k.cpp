#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

namespace {

struct WorkerScratch {
    Bytes current_tile;
    Bytes previous_tile;
};

struct EncodedTile {
    MotionResidual motion;
};

Bytes make_previous(std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t cs=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*cs);

    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*13u+y*7u+((x*y)%29u)*3u+((x/23u)^(y/17u))*11u)&255u);

    const auto cw=w/2;
    const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((71u+x*5u+y*9u+((x*y)%13u)*7u)&255u);
            b[ys+cs+i]=static_cast<Byte>((149u+x*11u+y*3u+((x+y)%17u)*5u)&255u);
        }
    return b;
}

Bytes make_current(ByteView prev,std::uint32_t w,std::uint32_t h) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t cs=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*cs);

    for(std::uint32_t y=0;y<h;++y) {
        for(std::uint32_t x=0;x<w;++x) {
            const int dx=(y<h/3)?1:((y<2*h/3)?-3:3);
            const int dy=(y<h/3)?-1:((y<2*h/3)?1:3);
            const int sx=static_cast<int>(x)+dx;
            const int sy=static_cast<int>(y)+dy;
            if(sx>=0 && sy>=0 && sx<static_cast<int>(w) && sy<static_cast<int>(h))
                out[static_cast<std::size_t>(y)*w+x]=
                    prev[static_cast<std::size_t>(sy)*w+static_cast<std::uint32_t>(sx)];
            else
                out[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>((x*19u+y*23u+31u)&255u);
        }
    }

    const auto cw=w/2;
    const auto ch=h/2;
    for(std::uint32_t y=0;y<ch;++y) {
        for(std::uint32_t x=0;x<cw;++x) {
            const auto dst=static_cast<std::size_t>(y)*cw+x;
            const auto sx=(x+cw-1)%cw;
            const auto sy=(y+1)%ch;
            out[ys+dst]=prev[ys+static_cast<std::size_t>(sy)*cw+sx];

            const auto sx2=(x+2)%cw;
            const auto sy2=(y+ch-1)%ch;
            out[ys+cs+dst]=prev[ys+cs+static_cast<std::size_t>(sy2)*cw+sx2];
        }
    }
    return out;
}

void extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,
                  const VideoTile& t,Bytes& out) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2;
    const auto ch=fh/2;
    const std::size_t cs=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2;
    const auto tch=t.height/2;
    const std::size_t tcs=static_cast<std::size_t>(tcw)*tch;

    out.resize(tys+2*tcs);
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
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+cs+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tcs+dst));
    }
}

template<class Fn>
void parallel_for(std::size_t count,std::uint32_t workers,Fn&& fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for(std::uint32_t worker=0;worker<workers;++worker) {
        pool.emplace_back([&,worker]{
            for(;;) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=count) break;
                fn(i,worker);
            }
        });
    }
    for(auto& t:pool) t.join();
}

std::uint64_t fnv1a(ByteView data,std::uint64_t h=1469598103934665603ull) {
    for(const auto b:data) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

struct Timing {
    double seconds{};
    std::uint64_t fingerprint{};
    std::uint64_t motion_bytes{};
};

Timing run_h3(ByteView cur,ByteView prev,const VideoTilePlan& plan,std::uint32_t workers) {
    std::vector<WorkerScratch> scratch(workers);
    std::vector<EncodedTile> encoded(plan.tiles.size());

    const auto t0=Clock::now();
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        const auto& tile=plan.tiles[i];
        auto& s=scratch[worker];
        extract_tile(cur,plan.frame_width,plan.frame_height,tile,s.current_tile);
        extract_tile(prev,plan.frame_width,plan.frame_height,tile,s.previous_tile);
        encoded[i].motion=AuroraVideoMotion::encode_mc8r4_h3(
            s.current_tile,s.previous_tile,tile.width,tile.height,
            DenseChromaPolicy::Floor);
    });
    const auto t1=Clock::now();

    std::uint64_t fp=1469598103934665603ull;
    std::uint64_t motion_bytes=0;
    for(std::size_t i=0;i<encoded.size();++i) {
        const auto& tile=plan.tiles[i];
        Bytes prev_tile;
        extract_tile(prev,plan.frame_width,plan.frame_height,tile,prev_tile);
        const auto decoded=AuroraVideoMotion::decode_mc8r4_dense(
            encoded[i].motion.motion_map,
            encoded[i].motion.residual_yuv420,
            prev_tile,tile.width,tile.height,
            DenseChromaPolicy::Floor);
        Bytes cur_tile;
        extract_tile(cur,plan.frame_width,plan.frame_height,tile,cur_tile);
        if(decoded!=cur_tile)
            throw std::runtime_error("native H3 tile roundtrip mismatch");

        fp=fnv1a(encoded[i].motion.motion_map,fp);
        fp=fnv1a(encoded[i].motion.residual_yuv420,fp);
        motion_bytes+=encoded[i].motion.motion_map.size();
    }

    return {
        std::chrono::duration<double>(t1-t0).count(),
        fp,
        motion_bytes
    };
}

Timing run_sparse(ByteView cur,ByteView prev,const VideoTilePlan& plan,std::uint32_t workers) {
    std::vector<WorkerScratch> scratch(workers);
    std::vector<EncodedTile> encoded(plan.tiles.size());

    const auto t0=Clock::now();
    parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        const auto& tile=plan.tiles[i];
        auto& s=scratch[worker];
        extract_tile(cur,plan.frame_width,plan.frame_height,tile,s.current_tile);
        extract_tile(prev,plan.frame_width,plan.frame_height,tile,s.previous_tile);
        encoded[i].motion=AuroraVideoMotion::encode_mc8r4(
            s.current_tile,s.previous_tile,tile.width,tile.height);
    });
    const auto t1=Clock::now();

    std::uint64_t fp=1469598103934665603ull;
    std::uint64_t motion_bytes=0;
    for(const auto& e:encoded) {
        fp=fnv1a(e.motion.motion_map,fp);
        fp=fnv1a(e.motion.residual_yuv420,fp);
        motion_bytes+=e.motion.motion_map.size();
    }
    return {
        std::chrono::duration<double>(t1-t0).count(),
        fp,
        motion_bytes
    };
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        const auto cfg=video_profile_config(VideoProfile::Balanced);
        const auto plan=make_video_tile_plan(
            w,h,cfg.tile_width,cfg.tile_height,
            cfg.tile_halo,cfg.max_concurrent_tiles);

        const auto prev=make_previous(w,h);
        const auto cur=make_current(prev,w,h);

        const auto sparse=run_sparse(cur,prev,plan,4);
        std::cout<<"AURORA_NATIVE_H3_SPARSE_REFERENCE"
                 <<" workers=4"
                 <<" seconds="<<sparse.seconds
                 <<" fps="<<(1.0/sparse.seconds)
                 <<" motion_bytes="<<sparse.motion_bytes
                 <<" fingerprint="<<sparse.fingerprint
                 <<"\n";

        std::uint64_t reference_fp=0;
        for(const auto workers:{1u,2u,4u,8u}) {
            const auto h3=run_h3(cur,prev,plan,workers);
            if(reference_fp==0) reference_fp=h3.fingerprint;
            else if(reference_fp!=h3.fingerprint)
                throw std::runtime_error("H3 output differs across worker counts");

            std::cout<<"AURORA_NATIVE_H3_4K_PASS"
                     <<" workers="<<workers
                     <<" seconds="<<h3.seconds
                     <<" fps="<<(1.0/h3.seconds)
                     <<" speed_vs_sparse4_x="<<(sparse.seconds/h3.seconds)
                     <<" motion_bytes="<<h3.motion_bytes
                     <<" fingerprint="<<h3.fingerprint
                     <<"\n";
        }

        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
