#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_inspection.hpp"
#include "kephir2/aur2_selection.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t bytes) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    std::size_t written = 0;
    while (written < bytes) {
        const auto n = std::min(pattern.size(), bytes - written);
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

std::uint64_t id_for(
    const std::vector<kephir2::aur2::FileEntry>& entries,
    const std::string& path) {

    for (const auto& entry : entries) {
        if (entry.path == path) return entry.entry_id;
    }
    throw std::runtime_error("test entry not found");
}

} // namespace

int main() {
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_selective_smoke";
    const auto input = root / "input";
    const auto output = root / "selected";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(input / "docs");
    std::filesystem::create_directories(input / "empty-dir");

    write_repeat(
        input / "docs" / "a.txt",
        "alpha text alpha text common words and sentences\n",
        64u * 1024u);
    write_repeat(
        input / "docs" / "b.txt",
        "beta text beta text common words and sentences\n",
        64u * 1024u);
    write_repeat(
        input / "binary.bin",
        std::string("\0\x01\0\x02", 4),
        32u * 1024u);
    std::ofstream(input / "empty.dat", std::ios::binary);

    NativeK75Backend backend;
    kephir2::aur2::ArchiveExecutor executor;
    const auto archive = executor.compress_directory(
        input,
        backend,
        BackendOptions{},
        Layout::Smart);

    const auto entries = list_entries(archive);
    const auto a_id = id_for(entries, "docs/a.txt");
    const auto empty_dir_id = id_for(entries, "empty-dir");
    const auto empty_file_id = id_for(entries, "empty.dat");

    const std::vector<std::uint64_t> selection{
        a_id,
        empty_dir_id,
        empty_file_id
    };

    extract_selected(
        archive,
        output,
        backend,
        selection);

    assert(std::filesystem::is_regular_file(output / "docs" / "a.txt"));
    assert(read_all(output / "docs" / "a.txt") == read_all(input / "docs" / "a.txt"));
    assert(!std::filesystem::exists(output / "docs" / "b.txt"));
    assert(!std::filesystem::exists(output / "binary.bin"));
    assert(std::filesystem::is_regular_file(output / "empty.dat"));
    assert(std::filesystem::file_size(output / "empty.dat") == 0);
    assert(std::filesystem::is_directory(output / "empty-dir"));

    bool invalid_rejected = false;
    try {
        const std::vector<std::uint64_t> invalid{999999};
        extract_selected(archive, output, backend, invalid);
    } catch (const std::invalid_argument&) {
        invalid_rejected = true;
    }
    assert(invalid_rejected);

    std::filesystem::remove_all(root);
    return 0;
}
