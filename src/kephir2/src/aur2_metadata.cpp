#include "kephir2/aur2_metadata.hpp"

#include "kephir2/archive.hpp"
#include "kephir2/aur2.hpp"
#include "kephir2/aur2_indexed_file.hpp"

#include <algorithm>
#include <chrono>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace kephir2::aur2 {
namespace {

Section& find_file_table(Container& container) {
    Section* found = nullptr;
    for (auto& section : container.sections) {
        if (section.type != static_cast<std::uint32_t>(SectionType::FileTable)) continue;
        if (found != nullptr) {
            throw std::runtime_error("duplicate AUR2 FILE_TABLE section");
        }
        found = &section;
    }
    if (found == nullptr) {
        throw std::runtime_error("missing AUR2 FILE_TABLE section");
    }
    return *found;
}

const Section& find_file_table(const Container& container) {
    const Section* found = nullptr;
    for (const auto& section : container.sections) {
        if (section.type != static_cast<std::uint32_t>(SectionType::FileTable)) continue;
        if (found != nullptr) {
            throw std::runtime_error("duplicate AUR2 FILE_TABLE section");
        }
        found = &section;
    }
    if (found == nullptr) {
        throw std::runtime_error("missing AUR2 FILE_TABLE section");
    }
    return *found;
}

std::filesystem::path path_from_utf8(const std::string& text) {
    std::u8string value;
    value.resize(text.size());
    std::transform(text.begin(), text.end(), value.begin(), [](char c) {
        return static_cast<char8_t>(static_cast<unsigned char>(c));
    });
    return std::filesystem::path(value);
}

std::uint32_t encode_permissions(std::filesystem::perms permissions) noexcept {
    using P = std::filesystem::perms;
    std::uint32_t out = kMetadataPermissionsPresent;
    const auto has = [permissions](P bit) { return (permissions & bit) != P::none; };

    if (has(P::owner_read)) out |= 0400u;
    if (has(P::owner_write)) out |= 0200u;
    if (has(P::owner_exec)) out |= 0100u;
    if (has(P::group_read)) out |= 0040u;
    if (has(P::group_write)) out |= 0020u;
    if (has(P::group_exec)) out |= 0010u;
    if (has(P::others_read)) out |= 0004u;
    if (has(P::others_write)) out |= 0002u;
    if (has(P::others_exec)) out |= 0001u;
    if (has(P::set_uid)) out |= 04000u;
    if (has(P::set_gid)) out |= 02000u;
    if (has(P::sticky_bit)) out |= 01000u;
    return out;
}

std::filesystem::perms decode_permissions(std::uint32_t attributes) noexcept {
    using P = std::filesystem::perms;
    P out = P::none;
    const auto has = [attributes](std::uint32_t bit) { return (attributes & bit) != 0; };

    if (has(0400u)) out |= P::owner_read;
    if (has(0200u)) out |= P::owner_write;
    if (has(0100u)) out |= P::owner_exec;
    if (has(0040u)) out |= P::group_read;
    if (has(0020u)) out |= P::group_write;
    if (has(0010u)) out |= P::group_exec;
    if (has(0004u)) out |= P::others_read;
    if (has(0002u)) out |= P::others_write;
    if (has(0001u)) out |= P::others_exec;
    if (has(04000u)) out |= P::set_uid;
    if (has(02000u)) out |= P::set_gid;
    if (has(01000u)) out |= P::sticky_bit;
    return out;
}

bool read_mtime_unix_ns(
    const std::filesystem::path& path,
    std::int64_t& unix_ns) noexcept {

    std::error_code ec;
    const auto file_time = std::filesystem::last_write_time(path, ec);
    if (ec) return false;

    const auto file_now = std::filesystem::file_time_type::clock::now();
    const auto system_now = std::chrono::system_clock::now();
    const auto system_time = system_now +
        std::chrono::duration_cast<std::chrono::system_clock::duration>(file_time - file_now);
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        system_time.time_since_epoch()).count();
    unix_ns = static_cast<std::int64_t>(ns);
    return true;
}

void apply_mtime(const std::filesystem::path& path, std::int64_t unix_ns) {
    const auto system_target = std::chrono::system_clock::time_point(
        std::chrono::duration_cast<std::chrono::system_clock::duration>(
            std::chrono::nanoseconds(unix_ns)));
    const auto file_now = std::filesystem::file_time_type::clock::now();
    const auto system_now = std::chrono::system_clock::now();
    const auto file_target = file_now +
        std::chrono::duration_cast<std::filesystem::file_time_type::duration>(
            system_target - system_now);

    std::error_code ec;
    std::filesystem::last_write_time(path, file_target, ec);
    if (ec) {
        throw std::runtime_error("unable to restore AUR2 modification timestamp");
    }
}

std::filesystem::path source_path_for_entry(
    const std::filesystem::path& source,
    const FileEntry& entry,
    bool source_is_directory) {

    if (!source_is_directory) return source;
    return source / path_from_utf8(entry.path);
}

void capture_entry_metadata(FileEntry& entry, const std::filesystem::path& path) {
    std::error_code ec;
    const auto status = std::filesystem::status(path, ec);
    entry.attributes = ec ? 0 : encode_permissions(status.permissions());

    std::int64_t mtime = 0;
    if (read_mtime_unix_ns(path, mtime)) {
        entry.mtime_unix_ns = mtime;
        entry.attributes |= kMetadataMtimePresent;
    } else {
        entry.mtime_unix_ns = 0;
    }
}

void apply_entry_metadata(
    const FileEntry& entry,
    const std::filesystem::path& output_directory) {

    const auto target = safe_archive_target(output_directory, entry.path);
    if (!std::filesystem::exists(target)) {
        throw std::runtime_error("AUR2 metadata target does not exist");
    }

    if ((entry.attributes & kMetadataPermissionsPresent) != 0) {
        std::error_code ec;
        std::filesystem::permissions(
            target,
            decode_permissions(entry.attributes & kMetadataPermissionMask),
            std::filesystem::perm_options::replace,
            ec);
        // Permission models differ substantially across host filesystems.
        // Unsupported bits are best-effort and never invalidate lossless data extraction.
    }

    if ((entry.attributes & kMetadataMtimePresent) != 0) {
        apply_mtime(target, entry.mtime_unix_ns);
    }
}

std::size_t path_depth(const std::string& path) noexcept {
    return 1u + static_cast<std::size_t>(std::count(path.begin(), path.end(), '/'));
}

void restore_entries_impl(
    std::span<const FileEntry> entries,
    const std::filesystem::path& output_directory,
    const std::unordered_set<std::uint64_t>* selected) {

    std::vector<const FileEntry*> files;
    std::vector<const FileEntry*> directories;
    files.reserve(entries.size());
    directories.reserve(entries.size());

    for (const auto& entry : entries) {
        if (selected != nullptr && selected->find(entry.entry_id) == selected->end()) continue;
        if (entry.type == EntryType::Directory) {
            directories.push_back(&entry);
        } else {
            files.push_back(&entry);
        }
    }

    for (const auto* entry : files) {
        apply_entry_metadata(*entry, output_directory);
    }

    // Creating children changes directory mtimes. Restore directories last,
    // deepest first, then walk rootward.
    std::sort(directories.begin(), directories.end(), [](const FileEntry* a, const FileEntry* b) {
        const auto ad = path_depth(a->path);
        const auto bd = path_depth(b->path);
        if (ad != bd) return ad > bd;
        return a->path > b->path;
    });
    for (const auto* entry : directories) {
        apply_entry_metadata(*entry, output_directory);
    }
}

void restore_archive_impl(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    const std::unordered_set<std::uint64_t>* selected) {

    const auto container = decode_container(archive);
    validate_container_structure(container);
    const auto entries = decode_file_table(find_file_table(container).payload);
    restore_entries_impl(entries, output_directory, selected);
}

} // namespace

ByteBuffer attach_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& source) {

    auto container = decode_container(archive);
    validate_container_structure(container);
    auto& table = find_file_table(container);
    auto entries = decode_file_table(table.payload);

    const bool source_is_directory = std::filesystem::is_directory(source);
    const bool source_is_file = std::filesystem::is_regular_file(source);
    if (!source_is_directory && !source_is_file) {
        throw std::runtime_error("AUR2 metadata source is not a file or directory");
    }
    if (source_is_file && (entries.size() != 1 || entries[0].type != EntryType::File)) {
        throw std::runtime_error("AUR2 metadata source/archive kind mismatch");
    }

    for (auto& entry : entries) {
        const auto path = source_path_for_entry(source, entry, source_is_directory);
        std::error_code ec;
        const auto status = std::filesystem::status(path, ec);
        if (ec || (entry.type == EntryType::Directory && !std::filesystem::is_directory(status))
            || (entry.type == EntryType::File && !std::filesystem::is_regular_file(status))) {
            throw std::runtime_error("AUR2 metadata source entry is missing or changed");
        }
        capture_entry_metadata(entry, path);
    }

    table.payload = encode_file_table(entries);
    validate_container_structure(container);
    return encode_container(container.header, container.sections);
}

void restore_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory) {

    restore_archive_impl(archive, output_directory, nullptr);
}

void restore_selected_filesystem_metadata(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids) {

    std::unordered_set<std::uint64_t> selected;
    selected.reserve(entry_ids.size());
    selected.insert(entry_ids.begin(), entry_ids.end());
    restore_archive_impl(archive, output_directory, &selected);
}

void restore_filesystem_metadata_entries(
    std::span<const FileEntry> entries,
    const std::filesystem::path& output_directory) {

    restore_entries_impl(entries, output_directory, nullptr);
}

void restore_selected_filesystem_metadata_entries(
    std::span<const FileEntry> entries,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids) {

    std::unordered_set<std::uint64_t> selected;
    selected.reserve(entry_ids.size());
    selected.insert(entry_ids.begin(), entry_ids.end());
    restore_entries_impl(entries, output_directory, &selected);
}

void restore_filesystem_metadata_file(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory) {

    const auto entries = list_indexed_file(archive);
    restore_filesystem_metadata_entries(entries, output_directory);
}

void restore_selected_filesystem_metadata_file(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    std::span<const std::uint64_t> entry_ids) {

    const auto entries = list_indexed_file(archive);
    restore_selected_filesystem_metadata_entries(entries, output_directory, entry_ids);
}

} // namespace kephir2::aur2
