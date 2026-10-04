#pragma once

#include "kephir2/aur2.hpp"
#include "kephir2/backend.hpp"

#include <cstdint>
#include <span>
#include <vector>

namespace kephir2::aur2 {

struct ArchiveInfo {
    std::uint16_t container_major{0};
    std::uint16_t container_minor{0};
    std::uint16_t codec_major{0};
    std::uint16_t codec_minor{0};
    std::uint64_t feature_flags{0};
    std::uint64_t entry_count{0};
    std::uint64_t logical_bytes{0};
    std::uint64_t archive_bytes{0};
    std::uint64_t stream_count{0};
    bool is_encrypted{false};
    bool integrity_available{false};

    bool operator==(const ArchiveInfo&) const = default;
};

[[nodiscard]] ArchiveInfo inspect_archive(
    std::span<const std::uint8_t> archive);

[[nodiscard]] std::vector<FileEntry> list_entries(
    std::span<const std::uint8_t> archive);

void test_archive(
    std::span<const std::uint8_t> archive,
    CompressionBackend& backend,
    const BackendOptions& options = {});

} // namespace kephir2::aur2
