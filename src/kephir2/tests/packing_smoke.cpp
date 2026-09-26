#include "kephir2/packing.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <span>
#include <string>
#include <vector>

namespace {

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t count) {

    std::ofstream out(path, std::ios::binary);
    for (std::size_t i = 0; i < count; ++i) {
        out.write(pattern.data(), static_cast<std::streamsize>(pattern.size()));
    }
}

} // namespace

int main() {
    using namespace kephir2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_packing_smoke";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root / "sub");

    write_repeat(
        root / "a.dat",
        "int f(int x){return x*x+17;}\n",
        64);
    write_repeat(
        root / "aa.dat",
        "int g(int x){return x+31;}\n",
        32);

    {
        std::ofstream out(root / "sub" / "b.dat", std::ios::binary);
        for (int i = 0; i < 4096; ++i) {
            const char v = static_cast<char>(i & 0x0f);
            out.write(&v, 1);
        }
    }

    write_repeat(
        root / "sub" / "c.dat",
        "ordinary prose words and spaces form a sentence.\n",
        64);

    ContentAnalyzer analyzer;
    const auto plan = build_directory_packing_plan(root, analyzer);

    assert(plan.files.size() == 4);
    assert(!plan.groups.empty());
    assert(!plan.manifest.empty());

    assert(plan.files[0].path == "a.dat");
    assert(plan.files[1].path == "aa.dat");
    assert(plan.files[2].path == "sub/b.dat");
    assert(plan.files[3].path == "sub/c.dat");

    std::uint64_t total_group_bytes = 0;
    for (const auto& group : plan.groups) {
        total_group_bytes += group.raw_length;

        std::uint64_t cursor = 0;
        for (const auto index : group.file_indices) {
            assert(index < plan.files.size());
            const auto& file = plan.files[index];
            assert(file.group_id < plan.groups.size());
            assert(file.group_name == group.name);
            assert(file.group_offset == cursor);
            cursor += file.size;
        }
        assert(cursor == group.raw_length);
    }

    std::uint64_t total_file_bytes = 0;
    for (const auto& file : plan.files) {
        total_file_bytes += file.size;
    }
    assert(total_group_bytes == total_file_bytes);

    // Every group source must reproduce the exact logical concatenation
    // without materializing that concatenation inside the source itself.
    for (std::size_t group_index = 0; group_index < plan.groups.size(); ++group_index) {
        const auto& group = plan.groups[group_index];
        PackedGroupSource source(root, plan, group_index);
        assert(source.size() == group.raw_length);

        std::vector<std::uint8_t> expected;
        expected.reserve(static_cast<std::size_t>(group.raw_length));
        for (const auto file_index : group.file_indices) {
            std::ifstream in(root / std::filesystem::u8path(
                plan.files[file_index].path.begin(),
                plan.files[file_index].path.end()), std::ios::binary);
            expected.insert(
                expected.end(),
                std::istreambuf_iterator<char>(in),
                std::istreambuf_iterator<char>());
        }

        std::vector<std::uint8_t> actual;
        actual.resize(expected.size());
        std::size_t cursor = 0;
        while (cursor < actual.size()) {
            const auto chunk = std::min<std::size_t>(7, actual.size() - cursor);
            const auto got = source.read(
                cursor,
                std::span<std::uint8_t>(actual.data() + cursor, chunk));
            assert(got == chunk);
            cursor += got;
        }
        assert(actual == expected);

        std::array<std::uint8_t, 8> eof{};
        assert(source.read(source.size(), eof) == 0);
        assert(source.read(source.size() + 100, eof) == 0);
    }

    const auto manifest_records =
        decode_manifest(plan.manifest, plan.groups.size());
    assert(manifest_records.size() == plan.files.size());

    for (std::size_t i = 0; i < plan.files.size(); ++i) {
        assert(manifest_records[i].path == plan.files[i].path);
        assert(manifest_records[i].group_id == plan.files[i].group_id);
        assert(manifest_records[i].size == plan.files[i].size);
    }

    std::filesystem::remove_all(root);
    return 0;
}
