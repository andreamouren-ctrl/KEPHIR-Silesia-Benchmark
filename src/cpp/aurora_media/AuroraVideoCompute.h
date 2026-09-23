#pragma once
#include "AuroraCodecInterfaces.h"
#include <cstdint>
#include <memory>
#include <string>

namespace aurora::media {

enum class VideoComputeBackend : std::uint8_t {
    CpuReference = 0,
    D3D12 = 1
};

struct VideoComputeCapabilities {
    VideoComputeBackend backend{VideoComputeBackend::CpuReference};
    bool available{false};
    bool hardware_accelerated{false};
    std::string adapter_name;
};

class IVideoMotionCompute {
public:
    virtual ~IVideoMotionCompute() = default;
    virtual VideoComputeCapabilities capabilities() const = 0;

    // Produces one candidate index per 8x8 luma block.
    virtual Bytes motion_map_mc8r4(ByteView current_yuv420,
                                   ByteView previous_yuv420,
                                   std::uint32_t width,
                                   std::uint32_t height) = 0;
};

std::unique_ptr<IVideoMotionCompute> make_cpu_video_motion_compute();

#if defined(_WIN32)
std::unique_ptr<IVideoMotionCompute> make_d3d12_video_motion_compute(bool force_warp = false);
#endif

} // namespace aurora::media
