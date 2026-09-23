#pragma once
#include "AuroraMediaError.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace aurora::media {

struct VideoTile {
    std::uint32_t x{};
    std::uint32_t y{};
    std::uint32_t width{};
    std::uint32_t height{};
    std::uint32_t index{};
};

struct VideoTilePlan {
    std::uint32_t frame_width{};
    std::uint32_t frame_height{};
    std::uint32_t tile_width{256};
    std::uint32_t tile_height{240};
    std::uint32_t halo{8};
    std::uint32_t max_concurrent_tiles{8};
    std::vector<VideoTile> tiles;

    std::size_t estimated_peak_bytes_per_tile() const {
        const std::uint64_t ew = static_cast<std::uint64_t>(tile_width) + 2ull * halo;
        const std::uint64_t eh = static_cast<std::uint64_t>(tile_height) + 2ull * halo;
        const std::uint64_t yuv420 = ew * eh * 3ull / 2ull;
        // current, reference, residual, reconstruction scratch
        return static_cast<std::size_t>(yuv420 * 4ull);
    }

    std::size_t estimated_peak_parallel_bytes() const {
        return estimated_peak_bytes_per_tile() * max_concurrent_tiles;
    }
};

inline VideoTilePlan make_video_tile_plan(std::uint32_t width,
                                          std::uint32_t height,
                                          std::uint32_t tile_width = 256,
                                          std::uint32_t tile_height = 240,
                                          std::uint32_t halo = 8,
                                          std::uint32_t max_concurrent_tiles = 8) {
    if(width == 0 || height == 0 || tile_width == 0 || tile_height == 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"invalid video tile geometry");
    if((tile_width % 16) != 0 || (tile_height % 16) != 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"tile geometry must align to 16 pixels");
    if(max_concurrent_tiles == 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"max_concurrent_tiles must be positive");

    VideoTilePlan plan;
    plan.frame_width = width;
    plan.frame_height = height;
    plan.tile_width = tile_width;
    plan.tile_height = tile_height;
    plan.halo = halo;
    plan.max_concurrent_tiles = max_concurrent_tiles;

    std::uint32_t idx = 0;
    for(std::uint32_t y=0; y<height; y+=tile_height) {
        for(std::uint32_t x=0; x<width; x+=tile_width) {
            plan.tiles.push_back(VideoTile{
                x, y,
                std::min(tile_width, width-x),
                std::min(tile_height, height-y),
                idx++
            });
        }
    }
    return plan;
}

} // namespace aurora::media
