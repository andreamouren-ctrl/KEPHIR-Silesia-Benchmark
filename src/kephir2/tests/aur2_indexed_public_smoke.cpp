#include "kephir2/kephir2_c.h"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_seek.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
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
    require(static_cast<bool>(out), "unable to create test input");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write test input");
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to open test archive");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create test archive");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to write test archive");
}

int count_entry(const kephir2_entry_info_v1* entry, void* user_data) {
    if (!entry || entry->struct_size != sizeof(kephir2_entry_info_v1)) {
        return 1;
    }
    auto* count = static_cast<std::size_t*>(user_data);
    ++(*count);
    return 0;
}

std::string status_message(
    const char* operation,
    kephir2_status status,
    const kephir2_result_v1& result) {

    return std::string(operation)
        + " failed: status=" + kephir2_status_name(status)
        + " message=" + result.message;
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
    require(engine != nullptr, "kephir2_create returned null");

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

    const auto compress_status = kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result);
    require(
        compress_status == KEPHIR2_OK,
        status_message("compress", compress_status, result));
    require(fs::is_regular_file(archive_path), "compress did not publish archive");
    require(fs::file_size(archive_path) >= kFixedHeaderSize, "published archive is truncated");

    kephir2_archive_info_v1 info{};
    info.struct_size = sizeof(info);
    const auto inspect_status = kephir2_inspect(engine, archive_s.c_str(), &info);
    require(inspect_status == KEPHIR2_OK, "indexed inspect failed");
    require((info.feature_flags & feature_bit(Feature::SeekIndex)) != 0,
            "public writer did not advertise SEEK_INDEX");
    require(info.entry_count >= 3, "unexpected indexed entry count");

    std::size_t listed = 0;
    require(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        count_entry,
        &listed) == KEPHIR2_OK,
        "indexed list failed");
    require(listed == info.entry_count, "indexed list count mismatch");

    const auto original = read_all(archive_path);
    require(original.size() >= kFixedHeaderSize, "read-back archive is truncated");
    const auto model = decode_container(original);
    require(!model.sections.empty(), "indexed archive has no sections");
    require(model.sections.front().type
        == static_cast<std::uint32_t>(SectionType::SeekIndex),
        "SEEK_INDEX is not the first section");
    const auto index = decode_seek_index(model.sections.front().payload);

    const SeekIndexRecord* data_record = nullptr;
    for (const auto& record : index) {
        if (record.section_type == static_cast<std::uint32_t>(SectionType::Data)) {
            data_record = &record;
            break;
        }
    }
    require(data_record != nullptr, "seek index has no DATA record");
    require(data_record->payload_size != 0, "DATA record is empty");

    // Corrupt compressed DATA only. Fast inspect/list must remain usable because
    // they do not read DATA. Deep test must detect the payload corruption.
    {
        std::fstream io(archive_path, std::ios::binary | std::ios::in | std::ios::out);
        require(static_cast<bool>(io), "unable to open archive for DATA corruption");
        io.seekg(static_cast<std::streamoff>(data_record->payload_offset));
        char value = 0;
        io.read(&value, 1);
        require(io.gcount() == 1, "unable to read DATA byte for corruption");
        value ^= 0x01;
        io.seekp(static_cast<std::streamoff>(data_record->payload_offset));
        io.write(&value, 1);
        require(static_cast<bool>(io), "unable to corrupt DATA byte");
    }

    info = {};
    info.struct_size = sizeof(info);
    require(kephir2_inspect(engine, archive_s.c_str(), &info) == KEPHIR2_OK,
            "fast inspect read or rejected corrupted DATA");
    listed = 0;
    require(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        count_entry,
        &listed) == KEPHIR2_OK,
        "fast list read or rejected corrupted DATA");
    require(listed == info.entry_count, "fast list count changed after DATA corruption");

    kephir2_result_v1 test_result{};
    test_result.struct_size = sizeof(test_result);
    const auto deep_status = kephir2_test_archive(
        engine,
        archive_s.c_str(),
        &options,
        &test_result);
    require(
        deep_status == KEPHIR2_INTEGRITY_ERROR,
        status_message("deep test after DATA corruption", deep_status, test_result));

    // Restore the valid archive, then corrupt only the seek-index payload.
    // Metadata operations must reject it instead of silently falling back.
    write_all(archive_path, original);
    {
        constexpr std::uint64_t kIndexMutationOffset =
            kFixedHeaderSize + kSectionHeaderSize + 20u;
        std::fstream io(archive_path, std::ios::binary | std::ios::in | std::ios::out);
        require(static_cast<bool>(io), "unable to open archive for TOC corruption");
        io.seekg(static_cast<std::streamoff>(kIndexMutationOffset));
        char value = 0;
        io.read(&value, 1);
        require(io.gcount() == 1, "unable to read TOC byte for corruption");
        value ^= 0x20;
        io.seekp(static_cast<std::streamoff>(kIndexMutationOffset));
        io.write(&value, 1);
        require(static_cast<bool>(io), "unable to corrupt TOC byte");
    }

    info = {};
    info.struct_size = sizeof(info);
    require(kephir2_inspect(
        engine,
        archive_s.c_str(),
        &info) == KEPHIR2_CORRUPT_ARCHIVE,
        "corrupted SEEK_INDEX was not rejected");

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
    require(kephir2_inspect(engine, legacy_s.c_str(), &info) == KEPHIR2_OK,
            "legacy AUR2 scan fallback failed");
    require((info.feature_flags & feature_bit(Feature::SeekIndex)) == 0,
            "legacy archive unexpectedly advertises SEEK_INDEX");
    require(info.entry_count == 1, "legacy fallback entry count mismatch");

    kephir2_destroy(engine);
    fs::remove_all(base);
    return 0;
}
