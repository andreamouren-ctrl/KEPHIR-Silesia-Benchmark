#include "kephir2/kephir2_c.h"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_ranged_file.hpp"

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::string utf8(const std::filesystem::path& path) {
    const auto value = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(value.data()),
        value.size());
}

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create file-backed extraction input");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write file-backed extraction input");
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to open file-backed extraction file");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to rewrite file-backed extraction archive");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to persist corrupted extraction archive");
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2::aur2;

    const auto base = fs::temp_directory_path() / "kephir2_aur2_file_extract_smoke";
    const auto input = base / "input";
    const auto archive = base / "input.aur";
    const auto output = base / "output";
    const auto corrupt_archive = base / "corrupt.aur";
    const auto corrupt_output = base / "corrupt_output";

    fs::remove_all(base);
    fs::create_directories(input / "empty-dir");
    fs::create_directories(input / "sub");

    write_repeat(
        input / "code.txt",
        "int transform(int x){ return x * x + 17; }\n",
        320u * 1024u);
    write_repeat(
        input / "sub" / "prose.txt",
        "ordinary prose words and spaces form a natural sentence. ",
        384u * 1024u);
    write_repeat(
        input / "sub" / "binary.dat",
        std::string("\x00\x01\x02\x03\x10\x20\x40\x80", 8),
        256u * 1024u);
    {
        std::ofstream empty(input / "empty.bin", std::ios::binary | std::ios::trunc);
        require(static_cast<bool>(empty), "unable to create empty extraction fixture");
    }

    auto* engine = kephir2_create();
    require(engine != nullptr, "kephir2_create returned null");

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.workers = 2;
    options.overwrite_output = 1;
    options.verify_integrity = 1;
    options.allow_local_experience = 0;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);
    const auto input_s = utf8(input);
    const auto archive_s = utf8(archive);
    require(kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK,
        std::string("fixture compression failed: ") + result.message);

    const auto output_s = utf8(output);
    result = {};
    result.struct_size = sizeof(result);
    require(kephir2_extract(
        engine,
        archive_s.c_str(),
        output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK,
        std::string("public file-backed extraction failed: ") + result.message);
    require(std::strstr(result.message, "file-backed") != nullptr,
            "public extraction did not report indexed file-backed path");

    require(read_all(input / "code.txt") == read_all(output / "code.txt"),
            "file-backed extraction code.txt mismatch");
    require(read_all(input / "sub" / "prose.txt")
        == read_all(output / "sub" / "prose.txt"),
        "file-backed extraction prose.txt mismatch");
    require(read_all(input / "sub" / "binary.dat")
        == read_all(output / "sub" / "binary.dat"),
        "file-backed extraction binary.dat mismatch");
    require(fs::is_regular_file(output / "empty.bin")
        && fs::file_size(output / "empty.bin") == 0,
        "file-backed extraction did not preserve empty file");
    require(fs::is_directory(output / "empty-dir"),
            "file-backed extraction did not preserve empty directory");

    // Corrupt DATA while leaving the TOC/layout intact. Public extraction must
    // reject the stream via its per-stream CRC before passing it to K75.
    auto bytes = read_all(archive);
    IndexedRangeReader reader(archive);
    const auto& data = reader.require_section(SectionType::Data);
    require(data.payload_size > 0, "file-backed extraction fixture has empty DATA");
    const auto corruption_offset = static_cast<std::size_t>(data.payload_offset);
    require(corruption_offset < bytes.size(), "DATA corruption offset out of range");
    bytes[corruption_offset] ^= 0x5au;
    write_all(corrupt_archive, bytes);

    result = {};
    result.struct_size = sizeof(result);
    const auto corrupt_archive_s = utf8(corrupt_archive);
    const auto corrupt_output_s = utf8(corrupt_output);
    const auto corrupt_status = kephir2_extract(
        engine,
        corrupt_archive_s.c_str(),
        corrupt_output_s.c_str(),
        &options,
        &result);
    require(corrupt_status == KEPHIR2_INTEGRITY_ERROR,
            std::string("public file-backed corruption status mismatch: ")
                + kephir2_status_name(corrupt_status)
                + " / " + result.message);

    kephir2_destroy(engine);
    fs::remove_all(base);
    return 0;
}
