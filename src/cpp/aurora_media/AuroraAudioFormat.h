#pragma once
#include "AuroraMediaContainer.h"
#include <cstdint>
#include <stdexcept>

namespace aurora::media {

enum class AudioChannelLayout : std::uint8_t {
    Unspecified = 0,
    Mono = 1,
    Stereo = 2,
    Surround51 = 3,
    Surround71 = 4,
    Custom = 15
};

constexpr std::uint8_t kAudioLayoutMask = 0x0f;

struct AudioFormat {
    std::uint32_t sample_rate{};
    std::uint16_t channels{};
    std::uint16_t bits_per_sample{};
    AudioChannelLayout layout{AudioChannelLayout::Unspecified};
    std::uint32_t recovery_frames{};
};

constexpr bool is_supported_pcm_bits(std::uint32_t bits) noexcept {
    return bits==16 || bits==24 || bits==32;
}

constexpr std::uint16_t channel_count_for_layout(AudioChannelLayout layout) noexcept {
    switch(layout) {
        case AudioChannelLayout::Mono: return 1;
        case AudioChannelLayout::Stereo: return 2;
        case AudioChannelLayout::Surround51: return 6;
        case AudioChannelLayout::Surround71: return 8;
        default: return 0;
    }
}

inline void validate_audio_format(const AudioFormat& f) {
    if(f.sample_rate < 8'000 || f.sample_rate > 768'000)
        throw std::runtime_error("unsupported audio sample rate");
    if(f.channels < 1 || f.channels > 32)
        throw std::runtime_error("unsupported audio channel count");
    if(!is_supported_pcm_bits(f.bits_per_sample))
        throw std::runtime_error("unsupported audio PCM bit depth");
    if(f.recovery_frames==0)
        throw std::runtime_error("invalid audio recovery frames");

    const auto expected=channel_count_for_layout(f.layout);
    if(expected!=0 && expected!=f.channels)
        throw std::runtime_error("audio channel layout/count mismatch");
}

inline AudioFormat audio_format_from_track(const Track& t) {
    if(t.type!=kTrackAudio || t.codec!=kCodecAuroraAudio)
        throw std::runtime_error("track is not AURORA audio");
    AudioFormat f{
        t.p1,
        static_cast<std::uint16_t>(t.p2),
        static_cast<std::uint16_t>(t.p3),
        static_cast<AudioChannelLayout>(t.flags & kAudioLayoutMask),
        t.p4
    };
    validate_audio_format(f);
    return f;
}

inline Track make_audio_track(std::uint8_t id,const AudioFormat& f,std::uint8_t extra_flags=0) {
    validate_audio_format(f);
    const auto flags=static_cast<std::uint8_t>(
        (extra_flags & static_cast<std::uint8_t>(~kAudioLayoutMask)) |
        (static_cast<std::uint8_t>(f.layout) & kAudioLayoutMask));
    return Track{
        id,kTrackAudio,kCodecAuroraAudio,flags,
        f.sample_rate,f.channels,f.bits_per_sample,f.recovery_frames
    };
}

} // namespace aurora::media
