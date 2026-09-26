#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace kephir2 {

using CompressedBlob = std::vector<std::uint8_t>;

class ByteSource {
public:
    virtual ~ByteSource() = default;

    [[nodiscard]] virtual std::uint64_t size() const noexcept = 0;

    // Reads up to destination.size() bytes starting at logical offset.
    // Returns the number of bytes read. Reading at EOF returns zero.
    [[nodiscard]] virtual std::size_t read(
        std::uint64_t offset,
        std::span<std::uint8_t> destination) const = 0;
};

class ByteSink {
public:
    virtual ~ByteSink() = default;

    // Writes bytes at logical offset. Implementations must either accept the
    // complete span or throw.
    virtual void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) = 0;
};

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

class CompressionBackend {
public:
    virtual ~CompressionBackend() = default;

    [[nodiscard]] virtual const char* name() const noexcept = 0;
    [[nodiscard]] virtual std::uint32_t format_version() const noexcept = 0;

    [[nodiscard]] virtual BackendEncodeResult encode(
        const ByteSource& input,
        const BackendOptions& options) = 0;

    [[nodiscard]] virtual BackendStats decode(
        std::span<const std::uint8_t> blob,
        std::uint64_t expected_raw_bytes,
        ByteSink& output,
        const BackendOptions& options) = 0;
};

} // namespace kephir2
