#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    std::size_t written = 0;
    while (written < size) {
        const auto n = std::min(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::vector<std::string> tree(const std::filesystem::path& root) {
    std::vector<std::string> out;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_symlink()) continue;
        const auto rel_u8 = entry.path().lexically_relative(root).generic_u8string();
        const std::string rel(
            reinterpret_cast<const char*>(rel_u8.data()),
            rel_u8.size());
        if (entry.is_directory()) {
            out.push_back("D:" + rel);
        } else if (entry.is_regular_file()) {
            out.push_back("F:" + rel);
        }
    }
    std::sort(out.begin(), out.end());
    return out;
}

void verify_tree(
    const std::filesystem::path& expected,
    const std::filesystem::path& actual) {

    assert(tree(expected) == tree(actual));
    for (const auto& entry : std::filesystem::recursive_directory_iterator(expected)) {
        if (!entry.is_regular_file() || entry.is_symlink()) continue;
        const auto rel = entry.path().lexically_relative(expected);
        assert(read_all(entry.path()) == read_all(actual / rel));
    }
}

} // namespace

int main() {
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto base = std::filesystem::temp_directory_path() / "kephir2_aur2_directory_k75_smoke";
    const auto input = base / "input";
    const auto smart_out = base / "smart_out";
    const auto flat_out = base / "flat_out";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(input / "empty-dir" / "nested-empty");
    std::filesystem::create_directories(input / "sub");

    write_repeat(
        input / "code.cpp",
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n",
        128u * 1024u);

    write_repeat(
        input / "sub" / "prose.txt",
        "ordinary prose words and spaces form a natural sentence. ",
        160u * 1024u);

    {
        std::ofstream out(input / "sub" / "binary.dat", std::ios::binary);
        for (int i = 0; i < 64 * 1024; ++i) {
            const std::array<char, 4> v{
                0,
                static_cast<char>(i & 0xff),
                0,
                static_cast<char>((i >> 3) & 0xff)
            };
            out.write(v.data(), static_cast<std::streamsize>(v.size()));
        }
    }

    std::ofstream(input / "empty-file.bin", std::ios::binary);

    NativeK75Backend backend;
    kephir2::aur2::ArchiveExecutor executor;

    const auto smart_archive = executor.compress_directory(
        input,
        backend,
        BackendOptions{},
        Layout::Smart);

    assert(smart_archive.size() > 64);
    assert(smart_archive[0] == 'A');
    assert(smart_archive[1] == 'U');
    assert(smart_archive[2] == 'R');
    assert(smart_archive[3] == '2');

    const auto smart_model = decode_container(smart_archive);
    validate_container_structure(smart_model);
    assert((smart_model.header.feature_flags & feature_bit(Feature::Directory)) != 0);
    assert((smart_model.header.feature_flags & feature_bit(Feature::Kephir2)) != 0);

    const auto smart_entries = decode_file_table(smart_model.sections[0].payload);
    bool saw_empty_dir = false;
    bool saw_empty_file = false;
    for (const auto& entry : smart_entries) {
        if (entry.type == EntryType::Directory && entry.path == "empty-dir/nested-empty") {
            saw_empty_dir = true;
        }
        if (entry.type == EntryType::File && entry.path == "empty-file.bin" && entry.logical_size == 0) {
            saw_empty_file = true;
        }
    }
    assert(saw_empty_dir);
    assert(saw_empty_file);

    executor.extract_directory(smart_archive, smart_out, backend);
    verify_tree(input, smart_out);

    const auto flat_archive = executor.compress_directory(
        input,
        backend,
        BackendOptions{},
        Layout::Flat);

    const auto flat_model = decode_container(flat_archive);
    validate_container_structure(flat_model);
    const auto flat_streams = decode_stream_table(flat_model.sections[2].payload);
    assert(flat_streams.size() == 1);

    executor.extract_directory(flat_archive, flat_out, backend);
    verify_tree(input, flat_out);

    std::filesystem::remove_all(base);
    return 0;
}
