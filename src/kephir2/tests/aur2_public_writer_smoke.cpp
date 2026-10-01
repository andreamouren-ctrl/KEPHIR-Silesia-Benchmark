#include "kephir2/kephir2_c.h"

#include <cassert>
#include <cstring>
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

std::vector<unsigned char> read_prefix(const std::filesystem::path& path, std::size_t count) {
    std::ifstream in(path, std::ios::binary);
    std::vector<unsigned char> out(count, 0);
    in.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(count));
    out.resize(static_cast<std::size_t>(in.gcount()));
    return out;
}

void assert_aur2_magic(const std::filesystem::path& path) {
    const auto prefix = read_prefix(path, 8);
    assert(prefix.size() == 8);
    assert(prefix[0] == 'A');
    assert(prefix[1] == 'U');
    assert(prefix[2] == 'R');
    assert(prefix[3] == '2');
    assert(prefix[4] == 0x0d);
    assert(prefix[5] == 0x0a);
    assert(prefix[6] == 0x1a);
    assert(prefix[7] == 0x0a);
}

void assert_file_backed_writer(const kephir2_result_v1& result) {
    assert(result.status == KEPHIR2_OK);
    assert(std::strstr(result.message, "file-backed") != nullptr);
}

} // namespace

int main() {
    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_public_writer_smoke";
    const auto file_input = root / "sample.txt";
    const auto file_archive = root / "sample.aur";
    const auto directory_input = root / "directory";
    const auto directory_archive = root / "directory.aur";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(directory_input / "empty-dir");

    {
        std::ofstream out(file_input, std::ios::binary | std::ios::trunc);
        out << "AUR2 public writer magic verification payload\n";
    }
    {
        std::ofstream out(directory_input / "data.txt", std::ios::binary | std::ios::trunc);
        out << "directory payload\n";
    }

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.overwrite_output = 1;
    options.verify_integrity = 1;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);

    const auto file_input_s = utf8(file_input);
    const auto file_archive_s = utf8(file_archive);
    assert(kephir2_compress(
        engine,
        file_input_s.c_str(),
        file_archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert_file_backed_writer(result);
    assert_aur2_magic(file_archive);

    kephir2_archive_info_v1 info{};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, file_archive_s.c_str(), &info) == KEPHIR2_OK);
    assert(info.container_major == 2);
    assert(info.integrity_available == 1);

    result = {};
    result.struct_size = sizeof(result);
    const auto directory_input_s = utf8(directory_input);
    const auto directory_archive_s = utf8(directory_archive);
    assert(kephir2_compress(
        engine,
        directory_input_s.c_str(),
        directory_archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert_file_backed_writer(result);
    assert_aur2_magic(directory_archive);

    info = {};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, directory_archive_s.c_str(), &info) == KEPHIR2_OK);
    assert(info.container_major == 2);
    assert(info.entry_count == 2);

    kephir2_destroy(engine);
    std::filesystem::remove_all(root);
    return 0;
}
