#include "AuroraVideoProfiles.h"
#include "AuroraVideoStreamScheduler.h"
#include "AuroraVideoTileCodec.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes synthetic_residual(const VideoTile& tile,std::uint64_t frame) {
    const std::size_t y = static_cast<std::size_t>(tile.width)*tile.height;
    const std::size_t uv = y/2;
    Bytes b(y+uv);
    for(std::size_t i=0;i<b.size();++i) {
        const int d = static_cast<int>((i + tile.index + frame) % 7) - 3;
        b[i]=static_cast<Byte>(d & 0xff);
    }
    return b;
}

int main() {
    try {
        const auto cfg=video_profile_config(VideoProfile::Streaming4K);
        auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,
                                       cfg.tile_halo,cfg.max_concurrent_tiles);
        VideoStreamScheduler sched(plan,cfg.recovery_interval_frames,270);
        if(sched.enqueue_frame(0)!=135)
            throw std::runtime_error("4K enqueue");

        AuroraVideoTileCodec codec;
        std::size_t jobs=0;
        std::size_t zz=0;
        std::size_t bytes=0;

        while(auto job=sched.pop()) {
            auto src=synthetic_residual(job->tile,job->frame_index);
            auto pkt=codec.encode_residual(src);
            auto dec=codec.decode_residual(pkt);
            if(dec!=src) throw std::runtime_error("tile residual roundtrip");
            if(pkt.mode==VideoResidualMode::ZigZagInter) ++zz;
            bytes += pkt.mapped_residuals.size();
            ++jobs;
        }

        if(jobs!=135 || zz!=135)
            throw std::runtime_error("unexpected 4K tile decisions");

        std::cout<<"VIDEO_4K_NATIVE_TILE_CODEC_PASS jobs="<<jobs
                 <<" mapped_bytes="<<bytes<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
