#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace kephir2::native37 {

[[nodiscard]] std::vector<std::uint8_t> compress_chunk(
    const std::vector<std::uint8_t>& raw);

[[nodiscard]] std::vector<std::uint8_t> decompress_chunk(
    const std::vector<std::uint8_t>& compressed,
    std::size_t raw_size);

} // namespace kephir2::native37
