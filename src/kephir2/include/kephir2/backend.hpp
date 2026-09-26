#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace kephir2 {

using CompressedBlob = std::vector<std::uint8_t>;

struct BackendOptions {
    std::size_t workers{0};
    bool allow_local_experience{true};
};

struct BackendStats {
    std::uint64_t input_bytes{0};
    std::uint64_t output_bytes{0};
    std::size_t workers_used{0};
};

struct BackendEncodeResult {
    CompressedBlob blob;
    BackendStats stats{};
};

struct BackendDecodeResult {
    std::vector<std::uint8_t> bytes;
    BackendStats stats{};
};

class CompressionBackend {
public:
    virtual ~CompressionBackend() = default;

    [[nodiscard]] virtual const char* name() const noexcept = 0;
    [[nodiscard]] virtual std::uint32_t format_version() const noexcept = 0;

    [[nodiscard]] virtual BackendEncodeResult encode(
        std::span<const std::uint8_t> input,
        const BackendOptions& options) = 0;

    [[nodiscard]] virtual BackendDecodeResult decode(
        std::span<const std::uint8_t> blob,
        std::uint64_t expected_raw_bytes,
        const BackendOptions& options) = 0;
};

} // namespace kephir2
