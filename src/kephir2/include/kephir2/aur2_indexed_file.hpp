#pragma once

#include "kephir2/aur2_inspection.hpp"

#include <filesystem>
#include <vector>

namespace kephir2::aur2 {

// Reads only the fixed header to determine whether the archive advertises a
// SEEK_INDEX. Invalid AUR2 headers are rejected rather than silently falling
// back to an untrusted scan path.
[[nodiscard]] bool has_seek_index_file(const std::filesystem::path& archive);

// Metadata-only operations for indexed AUR2 files. DATA is never loaded by
// these functions; use test_archive for deep payload verification.
[[nodiscard]] ArchiveInfo inspect_indexed_file(
    const std::filesystem::path& archive);

[[nodiscard]] std::vector<FileEntry> list_indexed_file(
    const std::filesystem::path& archive);

// Validates SEEK_INDEX CRC, section offsets/framing and complete file coverage
// by section records without reading DATA payload bytes.
void validate_seek_index_file(const std::filesystem::path& archive);

} // namespace kephir2::aur2
