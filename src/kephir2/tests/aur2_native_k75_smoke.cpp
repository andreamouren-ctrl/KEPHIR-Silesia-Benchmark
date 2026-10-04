#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::ofstream out(path, std::ios::binary);
    std::size_t written = 0;
    while (written < size) {
        const auto n = std::min(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        written += n;
    }
}

} // namespace

int main() {
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto root = std::filesystem::temp_directory_path() / "kephir2_aur2_native_k75_smoke";
    const auto input = root / "sample.dat";
    const auto empty = root / "empty.dat";
    const auto restored = root / "restored";
    const auto restored_empty = root / "restored_empty";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    write_repeat(
        input,
        "AURORA KEPHIR native container roundtrip data 0123456789\n",
        256u * 1024u);
    std::ofstream(empty, std::ios::binary);

    NativeK75Backend backend;
    kephir2::aur2::ArchiveExecutor executor;

    const auto archive = executor.compress_file(input, backend);
    assert(archive.size() > 64);
    assert(archive[0] == 'A');
    assert(archive[1] == 'U');
    assert(archive[2] == 'R');
    assert(archive[3] == '2');

    const auto model = decode_container(archive);
    validate_container_structure(model);
    assert(model.header.logical_size == std::filesystem::file_size(input));
    assert((model.header.feature_flags & feature_bit(Feature::Kephir2)) != 0);

    executor.extract_file(archive, restored, backend);
    assert(read_all(input) == read_all(restored / "sample.dat"));

    const auto empty_archive = executor.compress_file(empty, backend);
    const auto empty_model = decode_container(empty_archive);
    validate_container_structure(empty_model);
    assert(empty_model.header.logical_size == 0);

    executor.extract_file(empty_archive, restored_empty, backend);
    assert(std::filesystem::exists(restored_empty / "empty.dat"));
    assert(std::filesystem::file_size(restored_empty / "empty.dat") == 0);

    std::filesystem::remove_all(root);
    return 0;
}
