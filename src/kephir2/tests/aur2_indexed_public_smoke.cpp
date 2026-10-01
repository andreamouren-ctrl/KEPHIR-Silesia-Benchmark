#include "kephir2/kephir2_c.h"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_seek.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

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
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
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

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
}

int count_entry(const kephir2_entry_info_v1* entry, void* user_data) {
    assert(entry != nullptr);
    assert(entry->struct_size == sizeof(kephir2_entry_info_v1));
    auto* count = static_cast<std::size_t*>(user_data);
    ++(*count);
    return 0;
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto base = fs::temp_directory_path() / "kephir2_aur2_indexed_public_smoke";
    const auto input = base / "input";
    const auto archive_path = base / "indexed.aur";
    const auto legacy_path = base / "legacy.aur";
    fs::remove_all(base);
    fs::create_directories(input / "sub");

    write_repeat(
        input / "alpha.txt",
        "indexed metadata should not require reading compressed DATA.\n",
        128u * 1024u);
    write_repeat(
        input / "sub" / "beta.bin",
        "0123456789abcdef",
        96u * 1024u);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.workers = 1;
    options.overwrite_output = 1;
    options.verify_integrity = 1;
    options.allow_local_experience = 0;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);
    const auto input_s = utf8(input);
    const auto archive_s = utf8(archive_path);

    assert(kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);

    kephir2_archive_info_v1 info{};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, archive_s.c_str(), &info) == KEPHIR2_OK);
    assert((info.feature_flags & feature_bit(Feature::SeekIndex)) != 0);
    assert(info.entry_count >= 3);

    std::size_t listed = 0;
    assert(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        count_entry,
        &listed) == KEPHIR2_OK);
    assert(listed == info.entry_count);

    const auto original = read_all(archive_path);
    const auto model = decode_container(original);
    assert(!model.sections.empty());
    assert(model.sections.front().type
        == static_cast<std::uint32_t>(SectionType::SeekIndex));
    const auto index = decode_seek_index(model.sections.front().payload);

    const SeekIndexRecord* data_record = nullptr;
    for (const auto& record : index) {
        if (record.section_type == static_cast<std::uint32_t>(SectionType::Data)) {
            data_record = &record;
            break;
        }
    }
    assert(data_record != nullptr);
    assert(data_record->payload_size != 0);

    // Corrupt compressed DATA only. Fast inspect/list must remain usable because
    // they do not read DATA. Deep test must detect the payload corruption.
    {
        std::fstream io(archive_path, std::ios::binary | std::ios::in | std::ios::out);
        io.seekg(static_cast<std::streamoff>(data_record->payload_offset));
        char value = 0;
        io.read(&value, 1);
        value ^= 0x01;
        io.seekp(static_cast<std::streamoff>(data_record->payload_offset));
        io.write(&value, 1);
    }

    info = {};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, archive_s.c_str(), &info) == KEPHIR2_OK);
    listed = 0;
    assert(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        count_entry,
        &listed) == KEPHIR2_OK);
    assert(listed == info.entry_count);

    kephir2_result_v1 test_result{};
    test_result.struct_size = sizeof(test_result);
    assert(kephir2_test_archive(
        engine,
        archive_s.c_str(),
        &options,
        &test_result) == KEPHIR2_INTEGRITY_ERROR);

    // Restore the valid archive, then corrupt only the seek-index payload.
    // Metadata operations must reject it instead of silently falling back.
    write_all(archive_path, original);
    {
        constexpr std::uint64_t kIndexMutationOffset =
            kFixedHeaderSize + kSectionHeaderSize + 20u;
        std::fstream io(archive_path, std::ios::binary | std::ios::in | std::ios::out);
        io.seekg(static_cast<std::streamoff>(kIndexMutationOffset));
        char value = 0;
        io.read(&value, 1);
        value ^= 0x20;
        io.seekp(static_cast<std::streamoff>(kIndexMutationOffset));
        io.write(&value, 1);
    }

    info = {};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(
        engine,
        archive_s.c_str(),
        &info) == KEPHIR2_CORRUPT_ARCHIVE);

    // Legacy AUR2 without SEEK_INDEX must still use the scan fallback.
    NativeK75Backend backend;
    ArchiveExecutor executor;
    BackendOptions backend_options;
    backend_options.workers = 1;
    backend_options.allow_local_experience = false;
    const auto legacy = executor.compress_file(
        input / "alpha.txt",
        backend,
        backend_options);
    write_all(legacy_path, legacy);

    const auto legacy_s = utf8(legacy_path);
    info = {};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, legacy_s.c_str(), &info) == KEPHIR2_OK);
    assert((info.feature_flags & feature_bit(Feature::SeekIndex)) == 0);
    assert(info.entry_count == 1);

    kephir2_destroy(engine);
    fs::remove_all(base);
    return 0;
}
