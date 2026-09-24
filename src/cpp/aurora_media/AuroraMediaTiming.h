#pragma once
#include "AuroraMediaError.h"
#include <cstdint>
#include <limits>

namespace aurora::media {

inline std::uint64_t rational_timestamp(std::uint64_t index,
                                        std::uint64_t rate_num,
                                        std::uint64_t rate_den,
                                        std::uint32_t timescale) {
    if(rate_num==0 || rate_den==0 || timescale==0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"invalid rational media clock");

    const std::uint64_t whole=index/rate_num;
    const std::uint64_t rem=index%rate_num;

    if(whole>std::numeric_limits<std::uint64_t>::max()/rate_den)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"media timestamp overflow");
    const auto seconds_num=whole*rate_den;
    if(seconds_num>std::numeric_limits<std::uint64_t>::max()/timescale)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"media timestamp overflow");
    const auto base=seconds_num*timescale;

    if(rem>std::numeric_limits<std::uint64_t>::max()/rate_den)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"media timestamp overflow");
    const auto rem_num=rem*rate_den;
    if(rem_num>std::numeric_limits<std::uint64_t>::max()/timescale)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"media timestamp overflow");
    const auto scaled=rem_num*timescale;
    const auto frac=(scaled + rate_num/2)/rate_num;

    if(base>std::numeric_limits<std::uint64_t>::max()-frac)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"media timestamp overflow");
    return base+frac;
}

inline std::uint64_t video_pts(std::uint64_t frame_index,
                               std::uint32_t fps_num,
                               std::uint32_t fps_den,
                               std::uint32_t timescale) {
    return rational_timestamp(frame_index,fps_num,fps_den,timescale);
}

inline std::uint64_t audio_pts(std::uint64_t sample_index,
                               std::uint32_t sample_rate,
                               std::uint32_t timescale) {
    return rational_timestamp(sample_index,sample_rate,1,timescale);
}

} // namespace aurora::media
