#pragma once

#include "kephir2/backend.hpp"

#include <filesystem>

namespace kephir2::aur2 {

// Extracts an indexed AUR2 archive without materializing the complete container
// or DATA section. Metadata is read through SEEK_INDEX and exactly one
// compressed stream blob is resident at a time. This is bounded per stream;
// NativeK75Backend still requires each compressed stream as a contiguous span.
void extract_indexed_file_backed(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options = {});

} // namespace kephir2::aur2
