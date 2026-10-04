#include "kephir2/aur2_metadata.hpp"
#include "kephir2/kephir2_c.h"

#include <cassert>
#include <chrono>
#include <cmath>
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

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
}

void set_age(const std::filesystem::path& path, std::chrono::hours age) {
    std::error_code ec;
    const auto target = std::filesystem::file_time_type::clock::now()
        - std::chrono::duration_cast<std::filesystem::file_time_type::duration>(age);
    std::filesystem::last_write_time(path, target, ec);
    assert(!ec);
}

bool mtime_close(
    const std::filesystem::path& a,
    const std::filesystem::path& b,
    std::chrono::seconds tolerance = std::chrono::seconds(3)) {

    std::error_code ea, eb;
    const auto ta = std::filesystem::last_write_time(a, ea);
    const auto tb = std::filesystem::last_write_time(b, eb);
    if (ea || eb) return false;

    const auto delta = ta > tb ? ta - tb : tb - ta;
    return delta <= std::chrono::duration_cast<std::filesystem::file_time_type::duration>(tolerance);
}

struct EntrySnapshot {
    std::uint64_t id{0};
    std::string path;
    std::uint32_t attributes{0};
    std::int64_t mtime{0};
};

int collect_entry(const kephir2_entry_info_v1* entry, void* user_data) {
    auto* entries = static_cast<std::vector<EntrySnapshot>*>(user_data);
    entries->push_back({
        entry->entry_id,
        entry->path_utf8 ? entry->path_utf8 : "",
        entry->attributes,
        entry->mtime_unix_ns
    });
    return 0;
}

const EntrySnapshot& find_entry(
    const std::vector<EntrySnapshot>& entries,
    const std::string& path) {

    for (const auto& entry : entries) {
        if (entry.path == path) return entry;
    }
    assert(false && "metadata test entry missing");
    return entries.front();
}

} // namespace

int main() {
    using namespace kephir2::aur2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_metadata_smoke";
    const auto input = root / "input";
    const auto output = root / "output";
    const auto selected_output = root / "selected";
    const auto archive = root / "metadata.aur";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(input / "nested");
    std::filesystem::create_directories(input / "empty-dir");
    write_text(input / "root.txt", "root metadata payload\n");
    write_text(input / "nested" / "child.txt", "child metadata payload\n");

#ifndef _WIN32
    std::filesystem::permissions(
        input / "root.txt",
        std::filesystem::perms::owner_read |
            std::filesystem::perms::owner_write |
            std::filesystem::perms::group_read,
        std::filesystem::perm_options::replace);
    std::filesystem::permissions(
        input / "nested" / "child.txt",
        std::filesystem::perms::owner_read |
            std::filesystem::perms::owner_write,
        std::filesystem::perm_options::replace);
#endif

    // Set directory timestamps after all children have been created.
    set_age(input / "root.txt", std::chrono::hours(31));
    set_age(input / "nested" / "child.txt", std::chrono::hours(37));
    set_age(input / "empty-dir", std::chrono::hours(43));
    set_age(input / "nested", std::chrono::hours(47));

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.overwrite_output = 1;
    options.verify_integrity = 1;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);

    const auto input_s = utf8(input);
    const auto archive_s = utf8(archive);
    assert(kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);

    std::vector<EntrySnapshot> entries;
    assert(kephir2_list_entries(
        engine,
        archive_s.c_str(),
        collect_entry,
        &entries) == KEPHIR2_OK);
    assert(entries.size() == 4);

    const auto& root_file = find_entry(entries, "root.txt");
    const auto& child_file = find_entry(entries, "nested/child.txt");
    const auto& nested_dir = find_entry(entries, "nested");
    const auto& empty_dir = find_entry(entries, "empty-dir");

    for (const auto* entry : {&root_file, &child_file, &nested_dir, &empty_dir}) {
        assert((entry->attributes & kMetadataPermissionsPresent) != 0);
        assert((entry->attributes & kMetadataMtimePresent) != 0);
        assert(entry->mtime != 0);
    }

    const auto output_s = utf8(output);
    result = {};
    result.struct_size = sizeof(result);
    assert(kephir2_extract(
        engine,
        archive_s.c_str(),
        output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK);

    assert(mtime_close(input / "root.txt", output / "root.txt"));
    assert(mtime_close(input / "nested" / "child.txt", output / "nested" / "child.txt"));
    assert(mtime_close(input / "nested", output / "nested"));
    assert(mtime_close(input / "empty-dir", output / "empty-dir"));

#ifndef _WIN32
    const auto src_root_perms = std::filesystem::status(input / "root.txt").permissions();
    const auto dst_root_perms = std::filesystem::status(output / "root.txt").permissions();
    const auto mask = std::filesystem::perms::owner_all |
        std::filesystem::perms::group_all |
        std::filesystem::perms::others_all;
    assert((src_root_perms & mask) == (dst_root_perms & mask));
#endif

    // Selective extraction must restore metadata for the selected file too.
    const std::uint64_t selected_id = child_file.id;
    kephir2_selection_v1 selection{};
    selection.struct_size = sizeof(selection);
    selection.entry_ids = &selected_id;
    selection.entry_count = 1;

    const auto selected_output_s = utf8(selected_output);
    result = {};
    result.struct_size = sizeof(result);
    assert(kephir2_extract_selected(
        engine,
        archive_s.c_str(),
        selected_output_s.c_str(),
        &selection,
        &options,
        &result) == KEPHIR2_OK);
    assert(mtime_close(
        input / "nested" / "child.txt",
        selected_output / "nested" / "child.txt"));

    kephir2_destroy(engine);
    std::filesystem::remove_all(root);
    return 0;
}
