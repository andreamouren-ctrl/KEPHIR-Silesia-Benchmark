#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::media {

struct Limits {
    std::uint16_t max_tracks = 32;
    std::uint32_t max_packet_bytes = 64u * 1024u * 1024u;
    std::uint32_t max_index_entries = 4u * 1024u * 1024u;
    std::uint64_t max_index_bytes = 256ull * 1024ull * 1024ull;
    std::size_t max_stream_buffer_bytes = 128ull * 1024ull * 1024ull;
};

inline constexpr Limits kDefaultLimits{};

} // namespace aurora::media
