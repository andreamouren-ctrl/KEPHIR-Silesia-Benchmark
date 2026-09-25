#pragma once
#include "AuroraCodecInterfaces.h"
#include <cstdint>

namespace aurora::media {

enum class VideoProfile {
    Streaming4K,
    Balanced,
    MaxCompression
};

struct VideoProfileConfig {
    VideoProfile profile{VideoProfile::Streaming4K};
    std::uint32_t tile_width{256};
    std::uint32_t tile_height{240};
    std::uint32_t tile_halo{8};
    std::uint32_t max_concurrent_tiles{8};
    std::uint32_t recovery_interval_frames{60};
    std::uint32_t routing_horizon_frames{20};
    bool enable_high_motion_ap256{false};
    double high_motion_threshold{5.5};
    // KHEPRI FAST-D parser depth selected for this video profile.
    // The current research backend bakes these values at generation/build time;
    // they are profile metadata here, not a runtime switch inside one binary.
    std::uint32_t khepri_chain_depth{24};
    std::uint32_t khepri_lazy_depth{12};
};

inline VideoProfileConfig video_profile_config(VideoProfile p) {
    VideoProfileConfig c;
    c.profile = p;
    switch(p) {
        case VideoProfile::Streaming4K:
            c.tile_width = 256;
            c.tile_height = 240;
            c.tile_halo = 8;
            c.max_concurrent_tiles = 8;
            c.recovery_interval_frames = 60;
            c.routing_horizon_frames = 20;
            c.enable_high_motion_ap256 = false;
            c.khepri_chain_depth = 24;
            c.khepri_lazy_depth = 12;
            break;
        case VideoProfile::Balanced:
            c.tile_width = 256;
            c.tile_height = 240;
            c.tile_halo = 8;
            c.max_concurrent_tiles = 6;
            c.recovery_interval_frames = 60;
            c.routing_horizon_frames = 20;
            c.enable_high_motion_ap256 = true;
            c.high_motion_threshold = 6.5;
            c.khepri_chain_depth = 48;
            c.khepri_lazy_depth = 24;
            break;
        case VideoProfile::MaxCompression:
            c.tile_width = 256;
            c.tile_height = 240;
            c.tile_halo = 8;
            c.max_concurrent_tiles = 4;
            c.recovery_interval_frames = 120;
            c.routing_horizon_frames = 20;
            c.enable_high_motion_ap256 = true;
            c.high_motion_threshold = 5.5;
            c.khepri_chain_depth = 64;
            c.khepri_lazy_depth = 32;
            break;
    }
    return c;
}

} // namespace aurora::media
