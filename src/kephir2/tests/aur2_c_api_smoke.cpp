#include "kephir2/aur2_execution.hpp"
#include "kephir2/kephir2_c.h"
#include "kephir2/native_k75.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

std::string utf8(const std::filesystem::path& path) {
    const auto value = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(value.data()),
        value.size());
}

void write_bytes(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
}

struct ListedEntries {
    std::vector<std::string> paths;
    std::size_t files{0};
    std::size_t directories{0};
};

int collect_entry(const kephir2_entry_info_v1* entry, void* user_data) {
    assert(entry != nullptr);
    assert(entry->struct_size >= sizeof(kephir2_entry_info_v1));
    assert(entry->path_utf8 != nullptr);

    auto* listed = static_cast<ListedEntries*>(user_data);
    listed->paths.emplace_back(entry->path_utf8);
    if (entry->type == KEPHIR2_ENTRY_DIRECTORY) {
        ++listed->directories;
    } else {
        ++listed->files;
    }
    return 0;
}

} // namespace

int main() {
    using namespace kephir2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_c_api_smoke";
    const auto input = root / "input";
    const auto archive_path = root / "sample.aur";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(input / "docs");
    std::filesystem::create_directories(input / "empty-dir");

    {
        std::ofstream(input / "docs" / "readme.txt", std::ios::binary)
            << "AUR2 public C API verification payload\n";
        std::ofstream(input / "empty.bin", std::ios::binary);
    }

    NativeK75Backend backend;
    aur2::ArchiveExecutor writer;
    const auto archive = writer.compress_directory(
        input,
        backend,
        BackendOptions{},
        Layout::Smart);
    write_bytes(archive_path, archive);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    const auto archive_utf8 = utf8(archive_path);

    kephir2_archive_info_v1 info{};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, archive_utf8.c_str(), &info) == KEPHIR2_OK);
    assert(info.container_major == 2);
    assert(info.container_minor == 0);
    assert(info.codec_major == 2);
    assert(info.entry_count == 4);
    assert(info.integrity_available == 1);
    assert(info.is_encrypted == 0);
    assert(info.archive_bytes == archive.size());

    ListedEntries listed;
    assert(kephir2_list_entries(
        engine,
        archive_utf8.c_str(),
        collect_entry,
        &listed) == KEPHIR2_OK);
    assert(listed.paths.size() == 4);
    assert(listed.files == 2);
    assert(listed.directories == 2);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    assert(options.struct_size == sizeof(options));
    assert(options.profile == KEPHIR2_PROFILE_AUTO);
    assert(options.verify_integrity == 1);

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);
    assert(kephir2_test_archive(
        engine,
        archive_utf8.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert(result.status == KEPHIR2_OK);
    assert(result.input_bytes == archive.size());
    assert(result.output_bytes == info.logical_bytes);

    // A structurally invalid file must be rejected through the public ABI.
    auto truncated = archive;
    truncated.pop_back();
    const auto bad_path = root / "truncated.aur";
    write_bytes(bad_path, truncated);
    const auto bad_utf8 = utf8(bad_path);

    kephir2_archive_info_v1 bad_info{};
    bad_info.struct_size = sizeof(bad_info);
    const auto bad_status =
        kephir2_inspect(engine, bad_utf8.c_str(), &bad_info);
    assert(bad_status == KEPHIR2_CORRUPT_ARCHIVE
        || bad_status == KEPHIR2_INTEGRITY_ERROR);

    kephir2_destroy(engine);
    std::filesystem::remove_all(root);
    return 0;
}
