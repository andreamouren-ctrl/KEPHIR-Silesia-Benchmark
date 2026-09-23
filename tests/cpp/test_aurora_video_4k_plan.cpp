#include "AuroraVideoTilePlanner.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

int main() {
    try {
        const auto p = make_video_tile_plan(3840,2160,256,240,8,8);
        if(p.tiles.size()!=135) throw std::runtime_error("unexpected 4K tile count");
        if(p.tiles.front().width!=256 || p.tiles.front().height!=240)
            throw std::runtime_error("bad first tile");
        if(p.tiles.back().x!=3584 || p.tiles.back().y!=1920 ||
           p.tiles.back().width!=256 || p.tiles.back().height!=240)
            throw std::runtime_error("bad final tile");

        // Keep parallel scratch bounded well below the existing stream-buffer cap.
        if(p.estimated_peak_parallel_bytes() > 16u*1024u*1024u)
            throw std::runtime_error("4K tile working set too large");

        const auto odd = make_video_tile_plan(3860,2176,256,240,8,4);
        if(odd.tiles.back().width==0 || odd.tiles.back().height==0)
            throw std::runtime_error("edge tile failure");

        std::cout << "VIDEO_4K_TILE_PLAN_PASS tiles=" << p.tiles.size()
                  << " peak_parallel_bytes=" << p.estimated_peak_parallel_bytes() << "\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << "\n";
        return 1;
    }
}
