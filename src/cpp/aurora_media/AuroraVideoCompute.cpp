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
};

} // namespace

std::unique_ptr<IVideoMotionCompute> make_cpu_video_motion_compute() {
    return std::make_unique<CpuVideoMotionCompute>();
}

} // namespace aurora::media
