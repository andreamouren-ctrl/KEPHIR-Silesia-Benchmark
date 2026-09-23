#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace aurora::media {

constexpr std::uint8_t kVersion = 1;
constexpr std::uint8_t kTrackAudio = 1;
constexpr std::uint8_t kTrackVideo = 2;
constexpr std::uint8_t kCodecAuroraAudio = 1;
constexpr std::uint8_t kCodecAuroraVideo = 2;
constexpr std::uint8_t kPacketKey = 1;
constexpr std::uint8_t kPacketRecovery = 2;
constexpr std::uint32_t kDefaultTimescale = 1'000'000;

struct Track {
    std::uint8_t id{};
    std::uint8_t type{};
    std::uint8_t codec{};
    std::uint8_t flags{};
    std::uint32_t p1{}, p2{}, p3{}, p4{};
};

struct PacketInfo {
    std::uint8_t track_id{};
    std::uint8_t flags{};
    std::uint64_t pts{};
    std::uint64_t duration{};
    std::uint64_t file_offset{};
    std::uint32_t size{};
};

std::uint32_t crc32(const std::uint8_t* data, std::size_t size);

class Muxer {
public:
    Muxer(const std::filesystem::path& path, std::vector<Track> tracks,
          std::uint32_t timescale = kDefaultTimescale);
    ~Muxer();
    Muxer(const Muxer&) = delete;
    Muxer& operator=(const Muxer&) = delete;

    void write_packet(std::uint8_t track_id, std::uint64_t pts,
                      std::uint64_t duration,
                      const std::vector<std::uint8_t>& payload,
                      std::uint8_t flags = 0);
    void close();

private:
    std::ofstream out_;
    std::vector<Track> tracks_;
    std::vector<PacketInfo> index_;
    std::uint32_t timescale_{};
    bool closed_{false};
};

class Demuxer {
public:
    explicit Demuxer(const std::filesystem::path& path);

    const std::vector<Track>& tracks() const noexcept { return tracks_; }
    const std::vector<PacketInfo>& index() const noexcept { return index_; }
    std::uint32_t timescale() const noexcept { return timescale_; }

    std::vector<std::uint8_t> read_packet(const PacketInfo& e);
    std::optional<PacketInfo> seek(std::uint8_t track_id, std::uint64_t pts,
                                   bool recovery_only = true) const;

private:
    void read_header_and_tracks();
    void read_index();

    std::ifstream in_;
    std::vector<Track> tracks_;
    std::vector<PacketInfo> index_;
    std::uint32_t timescale_{};
    std::uint64_t data_start_{};
};

} // namespace aurora::media
