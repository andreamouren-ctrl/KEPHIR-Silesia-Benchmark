#include "kephir2/native37.hpp"

#include <cassert>
#include <cstdint>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> repeated(
    const std::string& pattern,
    std::size_t size) {

    std::vector<std::uint8_t> out;
    out.reserve(size);
    while (out.size() < size) {
        const auto n = std::min(pattern.size(), size - out.size());
        out.insert(out.end(), pattern.begin(), pattern.begin() + n);
    }
    return out;
}

std::vector<std::uint8_t> deterministic_noise(std::size_t size) {
    std::vector<std::uint8_t> out(size);
    std::uint32_t x = 0x12345678u;
    for (auto& b : out) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        b = static_cast<std::uint8_t>(x & 0xffu);
    }
    return out;
}

void check(const std::vector<std::uint8_t>& raw) {
    const auto compressed = kephir2::native37::compress_chunk(raw);
    const auto decoded =
        kephir2::native37::decompress_chunk(compressed, raw.size());
    assert(decoded == raw);
}

} // namespace

int main() {
    check({});
    check({0});
    check(std::vector<std::uint8_t>(4096, 0));
    check(repeated(
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n",
        64u * 1024u));
    check(repeated(
        "ordinary prose words and spaces form a natural sentence. ",
        128u * 1024u));
    check(deterministic_noise(128u * 1024u));
    check(deterministic_noise(512u * 1024u));
    return 0;
}
