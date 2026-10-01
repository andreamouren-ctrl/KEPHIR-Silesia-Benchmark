#pragma once

#include "kephir2/archive.hpp"

#include <cstdint>
#include <filesystem>
#include <span>

namespace kephir2::aur2 {

// FileEntry::attributes portable metadata encoding used by AUR2 v2.
// Low 12 bits contain POSIX-style rwx/special permission bits.
inline constexpr std::uint32_t kMetadataPermissionMask = 0x00000fffu;
inline constexpr std::uint32_t kMetadataPermissionsPresent = 1u << 31u;
inline constexpr std::uint32_t kMetadataMtimePresent = 1u << 30u;

// Rewrites only the AUR2 FILE_TABLE metadata for the supplied source.
// Compressed DATA and per-stream INTEGRITY records remain unchanged.
[[nodiscard]] ByteBuffer attach_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& source);

// Restores portable permissions and modification timestamps for extracted
// entries. Metadata restoration is best-effort for permission bits that the
// host filesystem cannot represent, but timestamp failures are reported.
void restore_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory);

// Same as above but only for the selected archive entry ids.
void restore_selected_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids);

} // namespace kephir2::aur2
