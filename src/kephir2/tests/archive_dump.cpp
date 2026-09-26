#include "kephir2/archive.hpp"

#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace {

std::string hex(const kephir2::ByteBuffer& data) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out;
    out.reserve(data.size() * 2);
    for (const auto b : data) {
        out.push_back(digits[(b >> 4) & 0x0f]);
        out.push_back(digits[b & 0x0f]);
    }
    return out;
}

} // namespace

int main() {
    using namespace kephir2;

    const std::vector<std::uint64_t> values{
        0,
        1,
        127,
        128,
        255,
        300,
        16384,
        0x1'0000'0000ull,
        0x7fff'ffff'ffff'ffffull,
    };

    ByteBuffer varints;
    for (const auto value : values) {
        put_varint(varints, value);
    }

    const std::string micro = std::string("docs/source/") + "\xc2\xb5" + ".dat";
    const std::vector<ManifestRecord> records{
        {"docs/readme.txt", 0, 12},
        {"docs/source/main.cpp", 1, 345},
        {micro, 2, 70000},
        {"z.bin", 1, 0x1'0000'0000ull},
    };

    const auto manifest = encode_manifest(records);

    const Kpf1FileEnvelope file_env{
        "sample.txt",
        ByteBuffer{0x00,0x01,0xff,'K','7','5'}
    };
    const auto file_archive = encode_kpf1_file(file_env);

    const Kpf1DirectoryEnvelope dir_env{
        {"g0","g1","g2"},
        manifest,
        {
            {12, ByteBuffer{0x10,0x11}},
            {0x1'0000'0200ull, ByteBuffer{0x20,0x21,0x22}},
            {70000, ByteBuffer{0x30}}
        }
    };
    const auto dir_archive = encode_kpf1_directory(dir_env);

    std::cout << "VARINT_HEX\t" << hex(varints) << '\n';
    std::cout << "MANIFEST_HEX\t" << hex(manifest) << '\n';
    std::cout << "FILE_KPF1_HEX\t" << hex(file_archive) << '\n';
    std::cout << "DIR_KPF1_HEX\t" << hex(dir_archive) << '\n';
    return 0;
}
