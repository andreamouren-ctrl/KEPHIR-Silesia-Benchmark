#pragma once
#include "AuroraMediaError.h"
#include <cstdint>
#include <span>
#include <vector>

namespace aurora::media {

using Byte = std::uint8_t;
using Bytes = std::vector<Byte>;
using ByteView = std::span<const Byte>;

struct AudioFormat {
    std::uint32_t sample_rate = 48'000;
    std::uint16_t channels = 2;
    std::uint16_t bits_per_sample = 16;
};

enum class ChromaFormat : std::uint8_t {
    Yuv420 = 0,
    Yuv422 = 1,
    Yuv444 = 2
};

enum class ColorPrimaries : std::uint8_t {
    Unspecified = 0,
    Bt709 = 1,
    Bt2020 = 2
};

enum class TransferCharacteristics : std::uint8_t {
    Unspecified = 0,
    SdrBt1886 = 1,
    PqSt2084 = 2,
    Hlg = 3
};

enum class MatrixCoefficients : std::uint8_t {
    Unspecified = 0,
    Bt709 = 1,
    Bt2020Ncl = 2,
    Identity = 3
};

enum class ColorRange : std::uint8_t {
    Limited = 0,
    Full = 1
};

struct HdrStaticMetadata {
    bool present = false;
    std::uint16_t max_cll_nits = 0;
    std::uint16_t max_fall_nits = 0;
    std::uint32_t mastering_min_luminance_1e4_nits = 0;
    std::uint32_t mastering_max_luminance_nits = 0;
};

struct VideoFormat {
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    std::uint32_t fps_num = 0;
    std::uint32_t fps_den = 1;
    std::uint8_t bit_depth = 8;
    ChromaFormat chroma = ChromaFormat::Yuv420;
    ColorPrimaries primaries = ColorPrimaries::Bt709;
    TransferCharacteristics transfer = TransferCharacteristics::SdrBt1886;
    MatrixCoefficients matrix = MatrixCoefficients::Bt709;
    ColorRange range = ColorRange::Limited;
    HdrStaticMetadata hdr{};
};

inline bool is_hdr(const VideoFormat& f) noexcept {
    return f.transfer == TransferCharacteristics::PqSt2084 ||
           f.transfer == TransferCharacteristics::Hlg;
}

inline void validate_video_format(const VideoFormat& f) {
    if(f.width == 0 || f.height == 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "video dimensions must be non-zero");
    if(f.fps_num == 0 || f.fps_den == 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "video frame rate must be non-zero");
    if(f.bit_depth != 8 && f.bit_depth != 10 &&
       f.bit_depth != 12 && f.bit_depth != 16)
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "unsupported video bit depth");

    if(f.chroma == ChromaFormat::Yuv420 &&
       ((f.width & 1u) != 0 || (f.height & 1u) != 0))
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "YUV420 requires even width and height");
    if(f.chroma == ChromaFormat::Yuv422 && (f.width & 1u) != 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "YUV422 requires even width");

    if(is_hdr(f)) {
        if(f.bit_depth < 10)
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "HDR requires at least 10-bit samples");
        if(f.primaries != ColorPrimaries::Bt2020)
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "HDR profile requires BT.2020 primaries");
        if(f.matrix != MatrixCoefficients::Bt2020Ncl &&
           f.matrix != MatrixCoefficients::Identity)
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "HDR profile requires BT.2020 or identity matrix");
    }

    if(f.hdr.present && !is_hdr(f))
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "HDR static metadata requires PQ or HLG transfer");
}

struct AudioEncodeConfig {
    AudioFormat format{};
    std::uint32_t packet_ms = 2000;
    std::uint32_t predictor_block_ms = 20;
};

struct VideoEncodeConfig {
    VideoFormat format{};
    std::uint32_t gop_frames = 10;
    std::uint32_t routing_horizon_frames = 20;
};

struct EncodedPacket {
    Bytes payload;
    bool key = false;
    bool recovery = true;
};

class IKhepriBackend {
public:
    virtual ~IKhepriBackend() = default;
    virtual Bytes encode(ByteView input) = 0;
    virtual Bytes decode(ByteView input) = 0;
};

class IAudioEncoder {
public:
    virtual ~IAudioEncoder() = default;
    virtual EncodedPacket encode(ByteView pcm) = 0;
};

class IAudioDecoder {
public:
    virtual ~IAudioDecoder() = default;
    virtual Bytes decode(ByteView payload) = 0;
};

class IVideoEncoder {
public:
    virtual ~IVideoEncoder() = default;
    virtual EncodedPacket encode(ByteView yuv) = 0;
};

class IVideoDecoder {
public:
    virtual ~IVideoDecoder() = default;
    virtual Bytes decode(ByteView payload) = 0;
};

} // namespace aurora::media
