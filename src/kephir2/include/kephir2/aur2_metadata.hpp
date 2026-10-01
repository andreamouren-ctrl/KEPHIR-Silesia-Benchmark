#pragma once

#include "kephir2/aur2.hpp"

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

// Restores portable permissions and modification timestamps from an in-memory
// AUR2 archive. Retained for compatibility with the original container path.
void restore_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory);

void restore_selected_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids);

// Metadata-only restore from already-decoded FILE_TABLE entries. These helpers
// never access compressed DATA and are the primitive used by file-backed paths.
void restore_filesystem_metadata_entries(
    std::span<const FileEntry> entries,
    const std::filesystem::path& output_directory);

void restore_selected_filesystem_metadata_entries(
    std::span<const FileEntry> entries,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids);

// Indexed file-backed variants. They read only SEEK_INDEX + FILE_TABLE and do
// not materialize the archive or DATA section.
void restore_filesystem_metadata_file(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory);

void restore_selected_filesystem_metadata_file(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids);

} // namespace kephir2::aur2
