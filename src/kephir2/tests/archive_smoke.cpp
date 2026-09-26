#include "kephir2/archive.hpp"

#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

bool throws_varint(std::vector<std::uint8_t> data) {
    try {
        std::size_t pos = 0;
        (void)kephir2::get_varint(data, pos);
        return false;
    } catch (const std::runtime_error&) {
        return true;
    }
}

bool throws_manifest(std::vector<std::uint8_t> data, std::uint64_t groups) {
    try {
        (void)kephir2::decode_manifest(data, groups);
        return false;
    } catch (const std::runtime_error&) {
        return true;
    }
}

bool throws_path(const std::filesystem::path& root, std::string_view rel) {
    try {
        (void)kephir2::safe_archive_target(root, rel);
        return false;
    } catch (const std::runtime_error&) {
        return true;
    }
}

} // namespace

int main() {
    using namespace kephir2;

    ByteBuffer varints;
    put_varint(varints, 0);
    put_varint(varints, 127);
    put_varint(varints, 128);
    put_varint(varints, 300);
    put_varint(varints, 16384);

    const ByteBuffer expected{
        0x00,
        0x7f,
        0x80, 0x01,
        0xac, 0x02,
        0x80, 0x80, 0x01
    };
    assert(varints == expected);

    std::size_t pos = 0;
    assert(get_varint(varints, pos) == 0);
    assert(get_varint(varints, pos) == 127);
    assert(get_varint(varints, pos) == 128);
    assert(get_varint(varints, pos) == 300);
    assert(get_varint(varints, pos) == 16384);
    assert(pos == varints.size());

    assert(throws_varint({0x80}));
    assert(throws_varint({0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x02}));

    const std::string micro = std::string("docs/source/") + "\xc2\xb5" + ".dat";
    const std::vector<ManifestRecord> records{
        {"docs/readme.txt", 0, 12},
        {"docs/source/main.cpp", 1, 345},
        {micro, 2, 70000},
        {"z.bin", 1, 0x1'0000'0000ull},
    };

    const auto encoded = encode_manifest(records);
    const auto decoded = decode_manifest(encoded, 3);
    assert(decoded == records);

    auto trailing = encoded;
    trailing.push_back(0);
    assert(throws_manifest(trailing, 3));
    assert(throws_manifest(encoded, 2));

    const Kpf1FileEnvelope file_env{
        "sample.txt",
        ByteBuffer{0x00,0x01,0xff,'K','7','5'}
    };
    const auto file_bytes = encode_kpf1_file(file_env);
    assert(decode_kpf1_file(file_bytes) == file_env);

    auto file_trailing = file_bytes;
    file_trailing.push_back(0);
    bool file_rejected = false;
    try {
        (void)decode_kpf1_file(file_trailing);
    } catch (const std::runtime_error&) {
        file_rejected = true;
    }
    assert(file_rejected);

    const Kpf1DirectoryEnvelope dir_env{
        {"g0","g1","g2"},
        encoded,
        {
            {12, ByteBuffer{0x10,0x11}},
            {0x1'0000'0200ull, ByteBuffer{0x20,0x21,0x22}},
            {70000, ByteBuffer{0x30}}
        }
    };
    const auto dir_bytes = encode_kpf1_directory(dir_env);
    assert(decode_kpf1_directory(dir_bytes) == dir_env);

    bool wrong_kind_rejected = false;
    try {
        (void)decode_kpf1_directory(file_bytes);
    } catch (const std::runtime_error&) {
        wrong_kind_rejected = true;
    }
    assert(wrong_kind_rejected);

    const auto root = std::filesystem::temp_directory_path() / "kephir2_archive_smoke";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root / "sub");

    {
        std::ofstream(root / "b.dat", std::ios::binary) << "b";
        std::ofstream(root / "sub" / "a.dat", std::ios::binary) << "a";
    }

    const auto target = safe_archive_target(root, "sub/new.dat");
    assert(target.filename() == "new.dat");
    assert(!throws_path(root, "sub/new.dat"));
    assert(throws_path(root, "../escape.dat"));
    assert(throws_path(root, "sub/../../escape.dat"));
    assert(throws_path(root, "/absolute.dat"));

    const auto files = collect_directory_files(root);
    assert(files.size() == 2);
    assert(files[0].lexically_relative(root).generic_string() == "b.dat");
    assert(files[1].lexically_relative(root).generic_string() == "sub/a.dat");

    std::filesystem::remove_all(root);
    return 0;
}
