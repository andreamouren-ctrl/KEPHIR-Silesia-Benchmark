#include "kephir2/kephir2_c.h"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_footer.hpp"
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

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create footer test input");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write footer test input");
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to open footer test archive");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to rewrite footer test archive");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to write footer test archive");
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

    const auto base = fs::temp_directory_path() / "kephir2_aur2_footer_smoke";
    const auto input = base / "input.bin";
    const auto archive_path = base / "footer.aur";
    const auto legacy_path = base / "legacy.aur";
    const auto extracted = base / "extracted";
    fs::remove_all(base);
    fs::create_directories(base);

    write_repeat(
        input,
        "AUR2 footer integrity protects metadata and complete publication.\n",
        192u * 1024u);

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

    auto status = kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result);
    require(status == KEPHIR2_OK, status_message("compress", status, result));

    const auto original = read_all(archive_path);
    validate_footer_integrity(original);

    const auto model = decode_container(original);
    require((model.header.feature_flags & kFeatureFooterIntegrity) != 0,
            "public writer did not advertise footer integrity");
    require(model.header.footer_offset != 0,
            "public writer did not publish footer_offset");
    require(!model.sections.empty(), "footer archive has no sections");
    require(model.sections.back().type == kFooterSectionType,
            "FTR1 is not the final AUR2 section");
    require(model.sections.back().flags == SectionFlagIgnorable,
            "FTR1 is not legacy-ignorable");

    require(model.sections.front().type
        == static_cast<std::uint32_t>(SectionType::SeekIndex),
        "footer archive lost SEEK_INDEX");
    const auto records = decode_seek_index(model.sections.front().payload);
    const SeekIndexRecord* footer_record = nullptr;
    const SeekIndexRecord* file_record = nullptr;
    for (const auto& record : records) {
        if (record.section_type == kFooterSectionType) footer_record = &record;
        if (record.section_type == static_cast<std::uint32_t>(SectionType::FileTable)) {
            file_record = &record;
        }
    }
    require(footer_record != nullptr, "SEEK_INDEX does not contain FTR1");
    require(file_record != nullptr, "SEEK_INDEX does not contain FILE_TABLE");
    require(footer_record->payload_size == kFooterPayloadSize,
            "SEEK_INDEX reports wrong footer size");
    require(model.header.footer_offset == footer_record->section_offset,
            "header footer_offset does not match SEEK_INDEX FTR1 offset");

    kephir2_result_v1 test_result{};
    test_result.struct_size = sizeof(test_result);
    status = kephir2_test_archive(
        engine,
        archive_s.c_str(),
        &options,
        &test_result);
    require(status == KEPHIR2_OK, status_message("test valid footer", status, test_result));

    const auto extracted_s = utf8(extracted);
    result = {};
    result.struct_size = sizeof(result);
    status = kephir2_extract(
        engine,
        archive_s.c_str(),
        extracted_s.c_str(),
        &options,
        &result);
    require(status == KEPHIR2_OK, status_message("extract footer", status, result));
    require(read_all(input) == read_all(extracted / input.filename()),
            "footer archive roundtrip mismatch");

    // Corrupt metadata, not DATA. Per-stream CRC cannot detect this, but the
    // global body checksum must reject it before the deep decoder runs.
    auto corrupt = original;
    require(file_record->payload_size > 2, "FILE_TABLE too small for corruption test");
    const auto metadata_offset = static_cast<std::size_t>(file_record->payload_offset + 1);
    require(metadata_offset < corrupt.size(), "metadata corruption offset out of range");
    corrupt[metadata_offset] ^= 0x10u;
    write_all(archive_path, corrupt);

    test_result = {};
    test_result.struct_size = sizeof(test_result);
    status = kephir2_test_archive(
        engine,
        archive_s.c_str(),
        &options,
        &test_result);
    require(status == KEPHIR2_INTEGRITY_ERROR,
            status_message("test metadata corruption", status, test_result));

    // Corrupt the footer's self checksum. This is distinct from body damage.
    corrupt = original;
    const auto footer_crc_offset = static_cast<std::size_t>(
        footer_record->payload_offset + 24u);
    require(footer_crc_offset < corrupt.size(), "footer CRC offset out of range");
    corrupt[footer_crc_offset] ^= 0x01u;
    write_all(archive_path, corrupt);

    test_result = {};
    test_result.struct_size = sizeof(test_result);
    status = kephir2_test_archive(
        engine,
        archive_s.c_str(),
        &options,
        &test_result);
    require(status == KEPHIR2_INTEGRITY_ERROR,
            status_message("test footer corruption", status, test_result));

    // Old AUR2 without FTR1 remains accepted and uses the existing deep path.
    NativeK75Backend backend;
    ArchiveExecutor executor;
    BackendOptions backend_options;
    backend_options.workers = 1;
    backend_options.allow_local_experience = false;
    const auto legacy = executor.compress_file(input, backend, backend_options);
    write_all(legacy_path, legacy);
    const auto legacy_s = utf8(legacy_path);

    test_result = {};
    test_result.struct_size = sizeof(test_result);
    status = kephir2_test_archive(
        engine,
        legacy_s.c_str(),
        &options,
        &test_result);
    require(status == KEPHIR2_OK,
            status_message("test legacy AUR2", status, test_result));

    kephir2_destroy(engine);
    fs::remove_all(base);
    return 0;
}
