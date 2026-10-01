#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_file_extract.hpp"
#include "kephir2/aur2_finalize_file.hpp"
#include "kephir2/aur2_footer.hpp"
#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/aur2_metadata.hpp"
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

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t bytes) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create finalizer fixture");
    std::size_t written = 0;
    while (written < bytes) {
        const auto n = (std::min)(pattern.size(), bytes - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write finalizer fixture");
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to read finalizer test file");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create base AUR2 file");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to write base AUR2 file");
}

const kephir2::aur2::Section& require_section(
    const kephir2::aur2::Container& container,
    kephir2::aur2::SectionType type) {

    const auto raw = static_cast<std::uint32_t>(type);
    const kephir2::aur2::Section* found = nullptr;
    for (const auto& section : container.sections) {
        if (section.type != raw) continue;
        require(found == nullptr, "duplicate section in finalizer test");
        found = &section;
    }
    require(found != nullptr, "missing section in finalizer test");
    return *found;
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto root = fs::temp_directory_path() / "kephir2_aur2_finalize_file_smoke";
    const auto input = root / "input";
    const auto base_path = root / "base.aur";
    const auto final_path = root / "final.aur";
    const auto output = root / "output";

    fs::remove_all(root);
    fs::create_directories(input / "empty-dir");
    fs::create_directories(input / "docs");

    write_repeat(
        input / "docs" / "story.txt",
        "file-backed finalization must never rewrite compressed DATA.\n",
        384u * 1024u);
    write_repeat(
        input / "binary.dat",
        std::string("\x00\x01\x02\x03\x10\x20\x40\x7f", 8),
        256u * 1024u);
    {
        std::ofstream empty(input / "empty.bin", std::ios::binary | std::ios::trunc);
        require(static_cast<bool>(empty), "unable to create finalizer empty file");
    }

    NativeK75Backend backend;
    ArchiveExecutor executor;
    BackendOptions options;
    options.workers = 2;
    options.allow_local_experience = false;

    const auto base = executor.compress_directory(
        input,
        backend,
        options,
        Layout::Smart);
    write_all(base_path, base);

    finalize_archive_file_backed(base_path, input, final_path);

    const auto final_bytes = read_all(final_path);
    validate_seek_index(final_bytes);
    validate_footer_integrity(final_bytes);

    const auto info = inspect_indexed_file(final_path);
    require(info.container_major == 2, "finalizer container major mismatch");
    require(info.entry_count == 5, "finalizer entry count mismatch");
    require(info.integrity_available, "finalizer lost per-stream integrity");
    require((info.feature_flags & feature_bit(Feature::SeekIndex)) != 0,
            "finalizer missing SEEK_INDEX feature");
    require((info.feature_flags & feature_bit(Feature::FooterIntegrity)) != 0,
            "finalizer missing footer feature");

    // The finalizer may rewrite metadata framing, but compressed DATA itself
    // must be byte-identical to the base compressor output.
    const auto base_model = decode_container(base);
    const auto final_model = decode_container(final_bytes);
    require(
        require_section(base_model, SectionType::Data).payload
            == require_section(final_model, SectionType::Data).payload,
        "file-backed finalizer changed compressed DATA bytes");

    const auto entries = list_indexed_file(final_path);
    bool saw_metadata = false;
    for (const auto& entry : entries) {
        if ((entry.attributes & kMetadataPermissionsPresent) != 0
            || (entry.attributes & kMetadataMtimePresent) != 0) {
            saw_metadata = true;
        }
    }
    require(saw_metadata, "file-backed finalizer did not capture filesystem metadata");

    extract_indexed_file_backed(final_path, output, backend, options);
    restore_filesystem_metadata_file(final_path, output);

    require(read_all(input / "docs" / "story.txt")
        == read_all(output / "docs" / "story.txt"),
        "finalized archive story roundtrip mismatch");
    require(read_all(input / "binary.dat") == read_all(output / "binary.dat"),
        "finalized archive binary roundtrip mismatch");
    require(fs::is_regular_file(output / "empty.bin")
        && fs::file_size(output / "empty.bin") == 0,
        "finalized archive empty file mismatch");
    require(fs::is_directory(output / "empty-dir"),
        "finalized archive empty directory mismatch");

    fs::remove_all(root);
    return 0;
}
