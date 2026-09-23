#pragma once
#include "AuroraCodecInterfaces.h"
#include <cstdint>

namespace aurora::media {

enum class VideoResidualMode : std::uint8_t {
    Mod8 = 0,
    ZigZagInter = 1
};

class AuroraVideoResidual final {
public:
    static Byte zigzag_byte(Byte value) noexcept;
    static Byte unzigzag_byte(Byte value) noexcept;

    static Bytes map(ByteView residuals, VideoResidualMode mode);
    static Bytes unmap(ByteView residuals, VideoResidualMode mode);

    static double mean_signed_magnitude(ByteView residuals) noexcept;
    static VideoResidualMode choose_mode(ByteView residuals,
                                         double threshold = 2.60) noexcept;
};

} // namespace aurora::media
