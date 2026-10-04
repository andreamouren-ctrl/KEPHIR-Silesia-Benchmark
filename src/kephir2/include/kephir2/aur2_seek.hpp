#pragma once

#include "kephir2/aur2.hpp"

#include <cstdint>
#include <span>
#include <vector>

namespace kephir2::aur2 {

inline constexpr std::uint16_t kSeekIndexVersion = 1;
inline constexpr std::uint16_t kSeekIndexRecordSize = 32;

struct SeekIndexRecord {
    std::uint32_t section_type{0};
    std::uint32_t section_flags{0};
    std::uint64_t section_offset{0};
    std::uint64_t payload_offset{0};
    std::uint64_t payload_size{0};

    bool operator==(const SeekIndexRecord&) const = default;
};

[[nodiscard]] ByteBuffer encode_seek_index(
    std::span<const SeekIndexRecord> records);

[[nodiscard]] std::vector<SeekIndexRecord> decode_seek_index(
    std::span<const std::uint8_t> payload);

// Rebuilds SEEK_INDEX as the first section. The index is derived metadata:
// decompression never depends on it, so legacy AUR2 archives remain valid.
[[nodiscard]] ByteBuffer attach_seek_index(
    std::span<const std::uint8_t> archive);

// Accepts legacy archives without SEEK_INDEX. If the feature flag or section is
// present, the complete index, offsets and CRC are checked strictly.
void validate_seek_index(std::span<const std::uint8_t> archive);

} // namespace kephir2::aur2
