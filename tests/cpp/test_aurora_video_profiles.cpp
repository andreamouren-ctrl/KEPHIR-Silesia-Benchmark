#include "AuroraVideoProfiles.h"
#include "AuroraVideoTilePlanner.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

int main() {
    try {
        const auto s = video_profile_config(VideoProfile::Streaming4K);
        if(s.enable_high_motion_ap256) throw std::runtime_error("streaming profile must avoid AP256 extra trial");
        if(s.tile_width!=256 || s.tile_height!=240 || s.max_concurrent_tiles!=8)
            throw std::runtime_error("streaming profile geometry");
        if(s.khepri_chain_depth!=24 || s.khepri_lazy_depth!=12)
            throw std::runtime_error("FAST KHEPRI depth profile");

        const auto b = video_profile_config(VideoProfile::Balanced);
        if(b.khepri_chain_depth!=48 || b.khepri_lazy_depth!=24)
            throw std::runtime_error("BALANCED KHEPRI depth profile");

        const auto m = video_profile_config(VideoProfile::MaxCompression);
        if(!m.enable_high_motion_ap256 || m.high_motion_threshold!=5.5)
            throw std::runtime_error("max compression profile");
        if(m.khepri_chain_depth!=64 || m.khepri_lazy_depth!=32)
            throw std::runtime_error("RATIO KHEPRI depth profile");

        const auto p = make_video_tile_plan(3840,2160,s.tile_width,s.tile_height,s.tile_halo,s.max_concurrent_tiles);
        if(p.tiles.size()!=135) throw std::runtime_error("4K profile tile count");

        std::cout<<"VIDEO_PROFILES_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
