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

} // namespace kephir2::aur2
