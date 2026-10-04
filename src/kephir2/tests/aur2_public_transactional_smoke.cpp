#include "kephir2/aur2.hpp"
#include "kephir2/aur2_ranged_file.hpp"
#include "kephir2/kephir2_c.h"

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
    const auto text = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(text.data()),
        text.size());
}

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create transactional public fixture");
    out << text;
    require(static_cast<bool>(out), "unable to persist transactional public fixture");
}

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create repeated transactional fixture");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write repeated transactional fixture");
        written += n;
    }
}

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to read transactional public fixture");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::string read_text(const std::filesystem::path& path) {
    const auto bytes = read_bytes(path);
    return std::string(bytes.begin(), bytes.end());
}

void write_bytes(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create corrupted transactional archive");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to persist corrupted transactional archive");
}

int cancel_immediately(void*) {
    return 1;
}

struct EntryCollector {
    std::uint64_t payload_id{UINT64_MAX};
};

int collect_entry(const kephir2_entry_info_v1* entry, void* user_data) {
    if (!entry || !user_data || !entry->path_utf8) return 0;
    auto& collector = *static_cast<EntryCollector*>(user_data);
    if (std::strcmp(entry->path_utf8, "payload.txt") == 0) {
        collector.payload_id = entry->entry_id;
    }
    return 0;
}

void assert_original_destination(const std::filesystem::path& output) {
    require(read_text(output / "keep.txt") == "keep-original",
            "transaction rollback modified unrelated file");
    require(read_text(output / "payload.txt") == "payload-old",
            "transaction rollback modified colliding file");
    require(read_text(output / "other.txt") == "other-old",
            "transaction rollback modified second colliding file");
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2::aur2;

    const auto root = fs::temp_directory_path() / "kephir2_aur2_public_transactional_smoke";
    const auto input = root / "input";
    const auto archive = root / "input.aur";
    const auto corrupt_archive = root / "corrupt.aur";
    const auto output = root / "output";

    fs::remove_all(root);
    fs::create_directories(input);
    write_repeat(
        input / "payload.txt",
        "transactional extraction payload line\n",
        384u * 1024u);
    write_repeat(
        input / "other.txt",
        "second transactional stream payload\n",
        256u * 1024u);

    auto* engine = kephir2_create();
    require(engine != nullptr, "kephir2_create returned null");

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.workers = 2;
    options.verify_integrity = 1;
    options.overwrite_output = 1;
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
        std::string("transactional fixture compression failed: ") + result.message);

    fs::create_directories(output);
    write_text(output / "keep.txt", "keep-original");
    write_text(output / "payload.txt", "payload-old");
    write_text(output / "other.txt", "other-old");

    // Corrupt only DATA. The public wrapper must discard its staging tree and
    // leave the original destination byte-for-byte unchanged.
    auto corrupt_bytes = read_bytes(archive);
    IndexedRangeReader reader(archive);
    const auto& data = reader.require_section(SectionType::Data);
    require(data.payload_size > 0, "transactional fixture has empty DATA");
    const auto corrupt_at = static_cast<std::size_t>(data.payload_offset);
    require(corrupt_at < corrupt_bytes.size(), "transactional corruption offset out of range");
    corrupt_bytes[corrupt_at] ^= 0x6du;
    write_bytes(corrupt_archive, corrupt_bytes);

    const auto corrupt_s = utf8(corrupt_archive);
    const auto output_s = utf8(output);
    result = {};
    result.struct_size = sizeof(result);
    const auto corrupt_status = kephir2_extract(
        engine,
        corrupt_s.c_str(),
        output_s.c_str(),
        &options,
        &result);
    require(corrupt_status == KEPHIR2_INTEGRITY_ERROR,
            std::string("transactional corruption status mismatch: ")
                + kephir2_status_name(corrupt_status)
                + " / " + result.message);
    assert_original_destination(output);

    // Cancellation must have the same rollback guarantee.
    auto cancel_options = options;
    cancel_options.cancel_callback = cancel_immediately;
    result = {};
    result.struct_size = sizeof(result);
    const auto cancel_status = kephir2_extract(
        engine,
        archive_s.c_str(),
        output_s.c_str(),
        &cancel_options,
        &result);
    require(cancel_status == KEPHIR2_CANCELLED,
            std::string("transactional cancellation status mismatch: ")
                + kephir2_status_name(cancel_status)
                + " / " + result.message);
    assert_original_destination(output);

    // Success commits atomically and preserves unrelated pre-existing files.
    result = {};
    result.struct_size = sizeof(result);
    require(kephir2_extract(
        engine,
        archive_s.c_str(),
        output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK,
        std::string("transactional public extraction failed: ") + result.message);
    require(std::strstr(result.message, "transactional") != nullptr,
            "public extraction did not report transactional commit");
    require(read_text(output / "keep.txt") == "keep-original",
            "transactional success lost unrelated file");
    require(read_bytes(output / "payload.txt") == read_bytes(input / "payload.txt"),
            "transactional success payload mismatch");
    require(read_bytes(output / "other.txt") == read_bytes(input / "other.txt"),
            "transactional success second payload mismatch");

    // Selective extraction uses the same transaction layer and must preserve an
    // unselected colliding file from the existing destination clone.
    write_text(output / "payload.txt", "payload-old");
    write_text(output / "other.txt", "other-old");

    EntryCollector collector;
    require(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        collect_entry,
        &collector) == KEPHIR2_OK,
        "unable to list entries for transactional selective test");
    require(collector.payload_id != UINT64_MAX,
            "payload entry id missing from transactional selective test");

    const std::uint64_t selected_ids[] = {collector.payload_id};
    kephir2_selection_v1 selection{};
    selection.struct_size = sizeof(selection);
    selection.entry_ids = selected_ids;
    selection.entry_count = 1;

    result = {};
    result.struct_size = sizeof(result);
    require(kephir2_extract_selected(
        engine,
        archive_s.c_str(),
        output_s.c_str(),
        &selection,
        &options,
        &result) == KEPHIR2_OK,
        std::string("transactional selective extraction failed: ") + result.message);
    require(std::strstr(result.message, "transactional") != nullptr,
            "selective extraction did not report transactional commit");
    require(read_bytes(output / "payload.txt") == read_bytes(input / "payload.txt"),
            "transactional selective payload mismatch");
    require(read_text(output / "other.txt") == "other-old",
            "transactional selective extraction modified unselected file");
    require(read_text(output / "keep.txt") == "keep-original",
            "transactional selective extraction lost unrelated file");

    kephir2_destroy(engine);
    fs::remove_all(root);
    return 0;
}
