#include "AuroraVideoResidual.h"

namespace aurora::media {

Byte AuroraVideoResidual::zigzag_byte(Byte value) noexcept {
    const int s = value < 128 ? static_cast<int>(value)
                              : static_cast<int>(value) - 256;
    const int z = s >= 0 ? (s << 1) : ((-s << 1) - 1);
    return static_cast<Byte>(z & 0xff);
}

Byte AuroraVideoResidual::unzigzag_byte(Byte value) noexcept {
    const int z = static_cast<int>(value);
    const int s = (z & 1) == 0 ? (z >> 1) : -((z + 1) >> 1);
    return static_cast<Byte>(s & 0xff);
}

Bytes AuroraVideoResidual::map(ByteView residuals, VideoResidualMode mode) {
    if(mode == VideoResidualMode::Mod8)
        return Bytes(residuals.begin(), residuals.end());

    Bytes out;
    out.reserve(residuals.size());
    for(const auto b : residuals)
        out.push_back(zigzag_byte(b));
    return out;
}

Bytes AuroraVideoResidual::unmap(ByteView residuals, VideoResidualMode mode) {
    if(mode == VideoResidualMode::Mod8)
        return Bytes(residuals.begin(), residuals.end());

    Bytes out;
    out.reserve(residuals.size());
    for(const auto b : residuals)
        out.push_back(unzigzag_byte(b));
    return out;
}

double AuroraVideoResidual::mean_signed_magnitude(ByteView residuals) noexcept {
    if(residuals.empty()) return 0.0;
    std::uint64_t sum = 0;
    for(const auto b : residuals)
        sum += b < 128 ? b : static_cast<Byte>(256 - static_cast<unsigned>(b));
    return static_cast<double>(sum) / static_cast<double>(residuals.size());
}

VideoResidualMode AuroraVideoResidual::choose_mode(ByteView residuals,
                                                   double threshold) noexcept {
    return mean_signed_magnitude(residuals) < threshold
        ? VideoResidualMode::ZigZagInter
        : VideoResidualMode::Mod8;
}

} // namespace aurora::media
