#pragma once
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <cstdint>

namespace aurora::media {

struct TileResidualPacket {
    VideoResidualMode mode{VideoResidualMode::Mod8};
    double mean_signed_magnitude{};
    Bytes mapped_residuals;
};

class AuroraVideoTileCodec final {
public:
    explicit AuroraVideoTileCodec(double zz_threshold = 2.60)
        : zz_threshold_(zz_threshold) {}

    TileResidualPacket encode_residual(ByteView residuals) const {
        TileResidualPacket p;
        p.mean_signed_magnitude = AuroraVideoResidual::mean_signed_magnitude(residuals);
        p.mode = p.mean_signed_magnitude < zz_threshold_
            ? VideoResidualMode::ZigZagInter
            : VideoResidualMode::Mod8;
        p.mapped_residuals = AuroraVideoResidual::map(residuals,p.mode);
        return p;
    }

    Bytes decode_residual(const TileResidualPacket& packet) const {
        return AuroraVideoResidual::unmap(packet.mapped_residuals,packet.mode);
    }

private:
    double zz_threshold_{2.60};
};

} // namespace aurora::media
