#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace kephir2::native37 {

[[nodiscard]] std::vector<std::uint8_t> encode_aur2_blob(
    std::span<const std::uint8_t> raw);

[[nodiscard]] std::vector<std::uint8_t> encode_aur2_blob(
    std::span<const std::uint8_t> raw,
    std::size_t chunk_bytes);

[[nodiscard]] std::vector<std::uint8_t> decode_aur2_blob(
    std::span<const std::uint8_t> blob);

} // namespace kephir2::native37
