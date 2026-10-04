#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_inspection.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
}

bool contains_path(
    const std::vector<kephir2::aur2::FileEntry>& entries,
    const std::string& path,
    kephir2::aur2::EntryType type) {

    return std::any_of(entries.begin(), entries.end(), [&](const auto& entry) {
        return entry.path == path && entry.type == type;
    });
}

bool inspection_rejects(std::span<const std::uint8_t> archive) {
    try {
        (void)kephir2::aur2::inspect_archive(archive);
        return false;
    } catch (...) {
        return true;
    }
}

} // namespace

int main() {
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto root =
        std::filesystem::temp_directory_path() / "kephir2_aur2_inspection_smoke";
    const auto input = root / "input";

    std::filesystem::remove_all(root);
    std::filesystem::create_directories(input / "sub");
    std::filesystem::create_directories(input / "empty-dir");

    const std::string a = "AUR2 inspection test text repeated repeated repeated.\n";
    const std::string b(8192, '\x5a');

    write_text(input / "a.txt", a);
    write_text(input / "sub" / "b.bin", b);
    write_text(input / "empty.dat", "");

    NativeK75Backend backend;
    kephir2::aur2::ArchiveExecutor executor;

    const auto archive = executor.compress_directory(
        input,
        backend,
        BackendOptions{},
        Layout::Smart);

    const auto info = inspect_archive(archive);
    assert(info.container_major == kContainerMajor);
    assert(info.container_minor == kContainerMinor);
    assert(info.codec_major == 2);
    assert(info.logical_bytes == a.size() + b.size());
    assert(info.archive_bytes == archive.size());
    assert(info.entry_count == 5);
    assert(info.stream_count >= 1);
    assert(!info.is_encrypted);
    assert(info.integrity_available);
    assert((info.feature_flags & feature_bit(Feature::Integrity)) != 0);

    const auto entries = list_entries(archive);
    assert(entries.size() == 5);
    assert(contains_path(entries, "a.txt", EntryType::File));
    assert(contains_path(entries, "sub/b.bin", EntryType::File));
    assert(contains_path(entries, "empty.dat", EntryType::File));
    assert(contains_path(entries, "sub", EntryType::Directory));
    assert(contains_path(entries, "empty-dir", EntryType::Directory));

    // Full decode verification without creating extracted files.
    test_archive(archive, backend);

    // Truncation must be rejected by inspection before any extraction attempt.
    auto truncated = archive;
    truncated.pop_back();
    assert(inspection_rejects(truncated));

    // Corrupt only the DATA payload while preserving the original INTEGRITY
    // section. Re-encoding refreshes framing/header bytes, so rejection here
    // specifically proves per-stream payload CRC32 validation works.
    auto corrupted_model = decode_container(archive);
    bool corrupted_data = false;
    for (auto& section : corrupted_model.sections) {
        if (section.type == static_cast<std::uint32_t>(SectionType::Data)
            && !section.payload.empty()) {
            section.payload.front() ^= 0x01u;
            corrupted_data = true;
            break;
        }
    }
    assert(corrupted_data);

    const auto corrupted = encode_container(
        corrupted_model.header,
        corrupted_model.sections);
    assert(inspection_rejects(corrupted));

    std::filesystem::remove_all(root);
    return 0;
}
