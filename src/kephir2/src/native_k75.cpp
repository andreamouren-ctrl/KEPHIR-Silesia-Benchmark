#include "kephir2/native_k75.hpp"

#include "kephir2/native37_blob.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <vector>

namespace kephir2 {

const char* NativeK75Backend::name() const noexcept {
    return "native-k75-exp37";
}

std::uint32_t NativeK75Backend::format_version() const noexcept {
    return 1;
}

BackendEncodeResult NativeK75Backend::encode(
    const ByteSource& input,
    const BackendOptions& options) {

    (void)options;

    if (input.size() > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("native K75 input exceeds addressable memory");
    }

    std::vector<std::uint8_t> raw(
        static_cast<std::size_t>(input.size()));

    std::uint64_t offset = 0;
    constexpr std::size_t kReadChunk = 1u * 1024u * 1024u;

    while (offset < input.size()) {
        const auto remaining = static_cast<std::size_t>(input.size() - offset);
        const auto want = std::min(kReadChunk, remaining);
        const auto got = input.read(
            offset,
            std::span<std::uint8_t>(
                raw.data() + static_cast<std::size_t>(offset),
                want));

        if (got == 0) {
            throw std::runtime_error("native K75 source ended before expected size");
        }
        offset += got;
    }

    auto blob = native37::encode_aur2_blob(raw);

    BackendEncodeResult result;
    result.stats.input_bytes = raw.size();
    result.stats.output_bytes = blob.size();
    result.stats.workers_used = 1;
    result.blob = std::move(blob);
    return result;
}

BackendStats NativeK75Backend::decode(
    std::span<const std::uint8_t> blob,
    std::uint64_t expected_raw_bytes,
    ByteSink& output,
    const BackendOptions& options) {

    (void)options;

    const auto raw = native37::decode_aur2_blob(blob);

    if (expected_raw_bytes != 0 && raw.size() != expected_raw_bytes) {
        throw std::runtime_error("native K75 decoded raw length mismatch");
    }

    constexpr std::size_t kWriteChunk = 1u * 1024u * 1024u;
    std::size_t offset = 0;

    while (offset < raw.size()) {
        const auto bytes = std::min(kWriteChunk, raw.size() - offset);
        output.write(
            offset,
            std::span<const std::uint8_t>(raw.data() + offset, bytes));
        offset += bytes;
    }

    BackendStats stats;
    stats.input_bytes = blob.size();
    stats.output_bytes = raw.size();
    stats.workers_used = 1;
    return stats;
}

} // namespace kephir2
