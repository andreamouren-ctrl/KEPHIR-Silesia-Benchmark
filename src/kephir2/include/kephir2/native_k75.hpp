#pragma once

#include "kephir2/backend.hpp"

namespace kephir2 {

class NativeK75Backend final : public CompressionBackend {
public:
    [[nodiscard]] const char* name() const noexcept override;
    [[nodiscard]] std::uint32_t format_version() const noexcept override;

    [[nodiscard]] BackendEncodeResult encode(
        const ByteSource& input,
        const BackendOptions& options) override;

    [[nodiscard]] BackendStats decode(
        std::span<const std::uint8_t> blob,
        std::uint64_t expected_raw_bytes,
        ByteSink& output,
        const BackendOptions& options) override;
};

} // namespace kephir2
