#pragma once

#include "kephir2/archive.hpp"
#include "kephir2/backend.hpp"
#include "kephir2/strategy.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>

namespace kephir2 {

struct ArchiveExecutionStats {
    std::uint64_t input_bytes{0};
    std::uint64_t output_bytes{0};
    std::size_t groups{0};
};

class ArchiveExecutor {
public:
    [[nodiscard]] ByteBuffer compress_file(
        const std::filesystem::path& input,
        CompressionBackend& backend,
        const BackendOptions& options = {}) const;

    [[nodiscard]] ByteBuffer compress_directory(
        const std::filesystem::path& root,
        CompressionBackend& backend,
        const BackendOptions& options = {},
        Layout layout = Layout::Smart) const;

    void extract_file(
        std::span<const std::uint8_t> archive,
        const std::filesystem::path& output_directory,
        CompressionBackend& backend,
        const BackendOptions& options = {}) const;

    void extract_directory(
        std::span<const std::uint8_t> archive,
        const std::filesystem::path& output_directory,
        CompressionBackend& backend,
        const BackendOptions& options = {}) const;
};

} // namespace kephir2
