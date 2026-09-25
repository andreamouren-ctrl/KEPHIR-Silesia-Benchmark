#pragma once
#include "AuroraMediaContainer.h"
#include "AuroraAudioFormat.h"
#include <cstdint>
#include <filesystem>
#include <optional>
#include <vector>

namespace aurora::media {

struct TimedPacket {
    PacketInfo info;
    std::vector<std::uint8_t> payload;
};

class MediaSession {
public:
    explicit MediaSession(const std::filesystem::path& path);

    const std::vector<Track>& tracks() const noexcept { return demux_.tracks(); }
    std::uint32_t timescale() const noexcept { return demux_.timescale(); }

    std::optional<Track> audio_track() const;
    std::optional<AudioFormat> audio_format() const;
    std::optional<Track> video_track() const;

    void reset();
    std::optional<TimedPacket> next();
    std::uint64_t seek(std::uint64_t requested_pts);

    std::size_t packet_count() const noexcept { return order_.size(); }
    std::size_t cursor() const noexcept { return cursor_; }

private:
    void validate_tracks();
    void build_order();

    Demuxer demux_;
    std::vector<PacketInfo> order_;
    std::size_t cursor_{0};
};

} // namespace aurora::media
