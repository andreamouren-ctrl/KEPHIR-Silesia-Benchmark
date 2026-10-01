#pragma once

#include "kephir2/backend.hpp"

#include <cstdint>
#include <filesystem>
#include <span>

namespace kephir2::aur2 {

void extract_selected(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    std::span<const std::uint64_t> entry_ids,
    const BackendOptions& options = {});

// Indexed file-backed selective extraction. Metadata is read through the
// SEEK_INDEX and only compressed streams referenced by selected entries are
// loaded. Peak archive-side memory is therefore bounded by the largest selected
// compressed stream rather than the complete AUR2 DATA section.
void extract_selected_indexed_file_backed(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    std::span<const std::uint64_t> entry_ids,
    const BackendOptions& options = {});

} // namespace kephir2::aur2
