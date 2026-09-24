#include "AuroraVideoCompute.h"
#include "AuroraVideoMotion.h"
#include "AuroraMediaError.h"

namespace aurora::media {
namespace {

class CpuVideoMotionCompute final : public IVideoMotionCompute {
public:
    VideoComputeCapabilities capabilities() const override {
        return VideoComputeCapabilities{
            VideoComputeBackend::CpuReference,
            true,
            false,
            "CPU reference"
        };
    }

    Bytes motion_map_mc8r4(ByteView current_yuv420,
                           ByteView previous_yuv420,
                           std::uint32_t width,
                           std::uint32_t height) override {
        return AuroraVideoMotion::encode_mc8r4(
            current_yuv420, previous_yuv420, width, height).motion_map;
    }

    Bytes residual_yuv420_mc8r4(ByteView current_yuv420,
                                ByteView previous_yuv420,
                                ByteView motion_map,
                                std::uint32_t width,
                                std::uint32_t height) override {
        const auto encoded=AuroraVideoMotion::encode_mc8r4(
            current_yuv420, previous_yuv420, width, height);
        if(encoded.motion_map!=Bytes(motion_map.begin(),motion_map.end()))
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "CPU reference motion map does not match MC8R4 selection");
        return encoded.residual_yuv420;
    }

    Bytes reconstruct_yuv420_mc8r4(ByteView previous_yuv420,
                                   ByteView residual_yuv420,
                                   ByteView motion_map,
                                   std::uint32_t width,
                                   std::uint32_t height) override {
        return AuroraVideoMotion::decode_mc8r4(
            motion_map,residual_yuv420,previous_yuv420,width,height);
    }
};

} // namespace

std::unique_ptr<IVideoMotionCompute> make_cpu_video_motion_compute() {
    return std::make_unique<CpuVideoMotionCompute>();
}

} // namespace aurora::media
