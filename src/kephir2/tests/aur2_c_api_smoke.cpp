#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/aur2_ranged_file.hpp"
#include "kephir2/aur2_streams.hpp"
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

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

struct ListedEntries {
    std::vector<std::string> paths;
    std::size_t files{0};
    std::size_t directories{0};
    std::uint64_t readme_id{0};
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
    if (std::string(entry->path_utf8) == "docs/readme.txt") {
        listed->readme_id = entry->entry_id;
    }
    return 0;
}

std::uint64_t stream_id_for(
    const std::vector<kephir2::aur2::FileEntry>& entries,
    const std::string& path) {

    for (const auto& entry : entries) {
        if (entry.path == path) return entry.stream_id;
    }
    assert(false && "test entry not found");
    return 0;
}

std::uint64_t stream_payload_offset_for(
    const std::vector<kephir2::aur2::StreamRecord>& streams,
    std::uint64_t stream_id) {

    for (const auto& stream : streams) {
        if (stream.stream_id == stream_id) return stream.payload_offset;
    }
    assert(false && "test stream not found");
    return 0;
}

} // namespace

int main() {
    using namespace kephir2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_c_api_smoke";
    const auto input = root / "input";
    const auto archive_path = root / "sample.aur";
    const auto selected_output = root / "selected";
    const auto selected_from_unrelated_corruption = root / "selected_unrelated_corrupt";
    const auto selected_corrupt_output = root / "selected_corrupt";
    const std::string readme_text = "AUR2 public C API verification payload\n";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(input / "docs");
    std::filesystem::create_directories(input / "empty-dir");

    {
        std::ofstream(input / "docs" / "readme.txt", std::ios::binary)
            << readme_text;
        std::ofstream(input / "empty.bin", std::ios::binary);
        std::ofstream binary(input / "binary.dat", std::ios::binary);
        for (int i = 0; i < 4096; ++i) {
            const char value = static_cast<char>((i * 37) & 0xff);
            binary.write(&value, 1);
        }
    }

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    assert(options.struct_size == sizeof(options));
    assert(options.profile == KEPHIR2_PROFILE_AUTO);
    assert(options.verify_integrity == 1);
    options.overwrite_output = 1;
    options.workers = 2;
    options.allow_local_experience = 0;

    const auto input_utf8 = utf8(input);
    const auto archive_utf8 = utf8(archive_path);
    kephir2_result_v1 compress_result{};
    compress_result.struct_size = sizeof(compress_result);
    assert(kephir2_compress(
        engine,
        input_utf8.c_str(),
        archive_utf8.c_str(),
        &options,
        &compress_result) == KEPHIR2_OK);

    kephir2_archive_info_v1 info{};
    info.struct_size = sizeof(info);
    assert(kephir2_inspect(engine, archive_utf8.c_str(), &info) == KEPHIR2_OK);
    assert(info.container_major == 2);
    assert(info.container_minor == 0);
    assert(info.codec_major == 2);
    assert(info.entry_count == 5);
    assert(info.integrity_available == 1);
    assert(info.is_encrypted == 0);
    assert(info.archive_bytes == std::filesystem::file_size(archive_path));

    ListedEntries listed;
    assert(kephir2_list_entries(
        engine,
        archive_utf8.c_str(),
        collect_entry,
        &listed) == KEPHIR2_OK);
    assert(listed.paths.size() == 5);
    assert(listed.files == 3);
    assert(listed.directories == 2);
    assert(listed.readme_id != 0);

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);
    assert(kephir2_test_archive(
        engine,
        archive_utf8.c_str(),
        &options,
        &result) == KEPHIR2_OK);
    assert(result.status == KEPHIR2_OK);
    assert(result.input_bytes == std::filesystem::file_size(archive_path));
    assert(result.output_bytes == info.logical_bytes);

    // Extract exactly one entry through the public ABI. Because the archive was
    // produced by the public writer, this must use the indexed file-backed path.
    const std::uint64_t selected_ids[] = {listed.readme_id};
    kephir2_selection_v1 selection{};
    selection.struct_size = sizeof(selection);
    selection.entry_ids = selected_ids;
    selection.entry_count = 1;

    const auto selected_utf8 = utf8(selected_output);
    kephir2_result_v1 selective_result{};
    selective_result.struct_size = sizeof(selective_result);
    assert(kephir2_extract_selected(
        engine,
        archive_utf8.c_str(),
        selected_utf8.c_str(),
        &selection,
        &options,
        &selective_result) == KEPHIR2_OK);
    assert(selective_result.status == KEPHIR2_OK);
    assert(std::strstr(selective_result.message, "file-backed selective") != nullptr);
    assert(read_text(selected_output / "docs" / "readme.txt") == readme_text);
    assert(!std::filesystem::exists(selected_output / "binary.dat"));
    assert(!std::filesystem::exists(selected_output / "empty.bin"));
    assert(!std::filesystem::exists(selected_output / "empty-dir"));

    aur2::IndexedRangeReader indexed(archive_path);
    const auto indexed_entries = aur2::list_indexed_file(archive_path);
    const auto streams = aur2::decode_stream_table(
        indexed.read_section_payload(aur2::SectionType::BlockTable));
    const auto& data = indexed.require_section(aur2::SectionType::Data);

    const auto readme_stream = stream_id_for(indexed_entries, "docs/readme.txt");
    const auto binary_stream = stream_id_for(indexed_entries, "binary.dat");
    assert(readme_stream != 0);
    assert(binary_stream != 0);

    const auto readme_offset = data.payload_offset
        + stream_payload_offset_for(streams, readme_stream);

    // When AUTO/SMART places the unrelated binary in another stream, corrupt
    // that stream and prove selective extraction does not read it. If AUTO
    // chooses FLAT for this tiny fixture, this optional optimization assertion
    // is skipped; selected-stream integrity below remains mandatory.
    if (binary_stream != readme_stream) {
        const auto binary_offset = data.payload_offset
            + stream_payload_offset_for(streams, binary_stream);
        auto unrelated_corrupt = read_bytes(archive_path);
        assert(binary_offset < unrelated_corrupt.size());
        unrelated_corrupt[static_cast<std::size_t>(binary_offset)] ^= 0x39u;
        const auto unrelated_path = root / "unrelated-corrupt.aur";
        write_bytes(unrelated_path, unrelated_corrupt);
        const auto unrelated_utf8 = utf8(unrelated_path);
        const auto unrelated_out_utf8 = utf8(selected_from_unrelated_corruption);

        selective_result = {};
        selective_result.struct_size = sizeof(selective_result);
        assert(kephir2_extract_selected(
            engine,
            unrelated_utf8.c_str(),
            unrelated_out_utf8.c_str(),
            &selection,
            &options,
            &selective_result) == KEPHIR2_OK);
        assert(read_text(selected_from_unrelated_corruption / "docs" / "readme.txt")
            == readme_text);
    }

    // Corrupt the selected stream itself. Per-stream integrity must reject it
    // before the K75 decoder consumes the damaged blob.
    auto selected_corrupt = read_bytes(archive_path);
    assert(readme_offset < selected_corrupt.size());
    selected_corrupt[static_cast<std::size_t>(readme_offset)] ^= 0x5au;
    const auto selected_corrupt_path = root / "selected-corrupt.aur";
    write_bytes(selected_corrupt_path, selected_corrupt);
    const auto selected_corrupt_utf8 = utf8(selected_corrupt_path);
    const auto selected_corrupt_out_utf8 = utf8(selected_corrupt_output);

    selective_result = {};
    selective_result.struct_size = sizeof(selective_result);
    assert(kephir2_extract_selected(
        engine,
        selected_corrupt_utf8.c_str(),
        selected_corrupt_out_utf8.c_str(),
        &selection,
        &options,
        &selective_result) == KEPHIR2_INTEGRITY_ERROR);

    // A structurally invalid file must still be rejected through the public ABI.
    auto truncated = read_bytes(archive_path);
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
