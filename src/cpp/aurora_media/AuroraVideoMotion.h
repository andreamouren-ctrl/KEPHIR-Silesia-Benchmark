#pragma once
#include "AuroraCodecInterfaces.h"
#include <cstdint>
#include <utility>
#include <vector>

namespace aurora::media {

struct MotionResidual {
    Bytes motion_map;
    Bytes residual_yuv420;
};

class AuroraVideoMotion final {
public:
    static std::vector<std::pair<int,int>> candidates(int radius = 4);

    static MotionResidual encode_mc8r4(ByteView current_yuv420,
                                      ByteView previous_yuv420,
                                      std::uint32_t width,
                                      std::uint32_t height);

    static MotionResidual encode_mc8r4_shortlist(ByteView current_yuv420,
                                                ByteView previous_yuv420,
                                                std::uint32_t width,
                                                std::uint32_t height,
                                                std::uint32_t shortlist);

    static MotionResidual encode_mc8r4_limited(ByteView current_yuv420,
                                               ByteView previous_yuv420,
                                               std::uint32_t width,
                                               std::uint32_t height,
                                               std::size_t max_candidates);

    static double sparse_luma_mad(ByteView current_yuv420,
                                  ByteView previous_yuv420,
                                  std::uint32_t width,
                                  std::uint32_t height,
                                  std::uint32_t sample_step = 8);

    static MotionResidual encode_mc8r4_adaptive(ByteView current_yuv420,
                                                ByteView previous_yuv420,
                                                std::uint32_t width,
                                                std::uint32_t height,
                                                double low_motion_threshold = 4.0,
                                                std::size_t low_motion_candidates = 9);

    static Bytes decode_mc8r4(ByteView motion_map,
                             ByteView residual_yuv420,
                             ByteView previous_yuv420,
                             std::uint32_t width,
                             std::uint32_t height);
};

} // namespace aurora::media
