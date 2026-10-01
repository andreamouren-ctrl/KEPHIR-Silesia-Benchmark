#pragma once

#include "kephir2/aur2.hpp"
#include "kephir2/backend.hpp"

#include <filesystem>
#include <span>

namespace kephir2::aur2 {

class ArchiveExecutor {
public:
    [[nodiscard]] ByteBuffer compress_file(
        const std::filesystem::path& input,
        CompressionBackend& backend,
        const BackendOptions& options = {}) const;

    void extract_file(
        std::span<const std::uint8_t> archive,
        const std::filesystem::path& output_directory,
        CompressionBackend& backend,
        const BackendOptions& options = {}) const;
};

} // namespace kephir2::aur2
