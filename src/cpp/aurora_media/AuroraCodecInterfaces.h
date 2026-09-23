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

struct VideoFormat {
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    std::uint32_t fps_num = 0;
    std::uint32_t fps_den = 1;
    std::uint8_t bit_depth = 8;
};

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
