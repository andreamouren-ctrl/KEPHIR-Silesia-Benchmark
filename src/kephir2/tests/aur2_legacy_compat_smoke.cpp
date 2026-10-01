#include "kephir2/execution.hpp"
#include "kephir2/kephir2_c.h"
#include "kephir2/native_k75.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

std::string utf8(const std::filesystem::path& path) {
    const auto s = path.generic_u8string();
    return std::string(reinterpret_cast<const char*>(s.data()), s.size());
}

void write_all(const std::filesystem::path& path, const std::vector<std::uint8_t>& bytes) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
}

} // namespace

int main() {
    using namespace kephir2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_legacy_compat_smoke";
    const auto single_input = root / "legacy.txt";
    const auto single_archive = root / "legacy-file.kpf";
    const auto single_output = root / "single-out";
    const auto dir_input = root / "legacy-dir";
    const auto dir_archive = root / "legacy-dir.kpf";
    const auto dir_output = root / "dir-out";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    write_text(single_input, "legacy KPF1 single file compatibility payload\n");
    write_text(dir_input / "a.txt", "alpha legacy payload\n");
    write_text(dir_input / "sub" / "b.txt", "beta legacy payload\n");

    NativeK75Backend backend;
    ArchiveExecutor legacy;

    const auto legacy_file_blob = legacy.compress_file(single_input, backend, BackendOptions{});
    assert(legacy_file_blob.size() >= 5);
    assert(legacy_file_blob[0] == 'K' && legacy_file_blob[1] == 'P'
        && legacy_file_blob[2] == 'F' && legacy_file_blob[3] == '1');
    write_all(single_archive, legacy_file_blob);

    const auto legacy_dir_blob = legacy.compress_directory(
        dir_input,
        backend,
        BackendOptions{},
        Layout::Smart);
    assert(legacy_dir_blob.size() >= 5);
    assert(legacy_dir_blob[0] == 'K' && legacy_dir_blob[1] == 'P'
        && legacy_dir_blob[2] == 'F' && legacy_dir_blob[3] == '1');
    write_all(dir_archive, legacy_dir_blob);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.overwrite_output = 1;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);

    const auto single_archive_s = utf8(single_archive);
    const auto single_output_s = utf8(single_output);
    assert(kephir2_extract(
        engine,
        single_archive_s.c_str(),
        single_output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert(read_all(single_input) == read_all(single_output / single_input.filename()));

    const auto dir_archive_s = utf8(dir_archive);
    const auto dir_output_s = utf8(dir_output);
    result = {};
    result.struct_size = sizeof(result);
    assert(kephir2_extract(
        engine,
        dir_archive_s.c_str(),
        dir_output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert(read_all(dir_input / "a.txt") == read_all(dir_output / "a.txt"));
    assert(read_all(dir_input / "sub" / "b.txt") == read_all(dir_output / "sub" / "b.txt"));

    kephir2_destroy(engine);
    std::filesystem::remove_all(root);
    return 0;
}
