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

    static Bytes decode_mc8r4(ByteView motion_map,
                             ByteView residual_yuv420,
                             ByteView previous_yuv420,
                             std::uint32_t width,
                             std::uint32_t height);
};

} // namespace aurora::media
