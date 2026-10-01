#include "kephir2/kephir2_c.h"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_ranged_file.hpp"

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
    require(static_cast<bool>(out), "unable to create ranged-reader input");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write ranged-reader input");
        written += n;
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to open ranged-reader archive");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2::aur2;

    const auto base = fs::temp_directory_path() / "kephir2_aur2_ranged_file_smoke";
    const auto input = base / "input.txt";
    const auto archive = base / "input.aur";
    fs::remove_all(base);
    fs::create_directories(base);

    write_repeat(
        input,
        "AUR2 indexed ranged reads must never require loading the complete DATA section.\n",
        512u * 1024u);

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
    const auto archive_s = utf8(archive);
    require(kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result) == KEPHIR2_OK,
        std::string("public ranged-reader fixture compression failed: ") + result.message);

    IndexedRangeReader reader(archive);
    require(reader.archive_size() == fs::file_size(archive),
            "ranged reader archive size mismatch");
    require((reader.header().feature_flags & feature_bit(Feature::SeekIndex)) != 0,
            "ranged reader fixture lost SEEK_INDEX");
    require(reader.header().footer_offset != 0,
            "ranged reader fixture lost footer_offset");

    const auto file_table_bytes = reader.read_section_payload(SectionType::FileTable);
    const auto entries = decode_file_table(file_table_bytes);
    require(entries.size() == 1 && entries[0].type == EntryType::File,
            "ranged reader FILE_TABLE mismatch");

    const auto block_table = reader.read_section_payload(SectionType::BlockTable);
    const auto streams = decode_stream_table(block_table);
    require(streams.size() == 1, "ranged reader expected one stream");

    const auto integrity_bytes = reader.read_section_payload(SectionType::Integrity);
    const auto integrity = decode_integrity_table(integrity_bytes);
    require(integrity.size() == 1, "ranged reader expected one integrity record");
    require(integrity[0].stream_id == streams[0].stream_id,
            "ranged reader integrity stream mismatch");

    const auto& data_record = reader.require_section(SectionType::Data);
    require(data_record.payload_size == streams[0].compressed_size,
            "ranged reader DATA size/stream size mismatch");

    const auto probe_size = (std::min<std::uint64_t>)(4096u, data_record.payload_size);
    const auto probe = reader.read_section_range(SectionType::Data, 0, probe_size);
    require(probe.size() == probe_size, "ranged reader probe length mismatch");

    // Comparison against the fixture bytes is test-only. The production ranged
    // reader itself never materializes the whole archive.
    const auto complete = read_all(archive);
    require(data_record.payload_offset + probe_size <= complete.size(),
            "ranged reader DATA probe exceeds fixture");
    require(std::equal(
        probe.begin(),
        probe.end(),
        complete.begin() + static_cast<std::ptrdiff_t>(data_record.payload_offset)),
        "ranged reader DATA probe differs from on-disk bytes");

    const auto compressed_stream = reader.read_section_range(
        SectionType::Data,
        streams[0].payload_offset,
        streams[0].compressed_size);
    require(crc32(compressed_stream) == integrity[0].payload_crc32,
            "ranged reader stream CRC mismatch");

    bool rejected = false;
    try {
        (void)reader.read_section_range(
            SectionType::Data,
            data_record.payload_size,
            1);
    } catch (const std::out_of_range&) {
        rejected = true;
    }
    require(rejected, "ranged reader accepted out-of-bounds section read");

    kephir2_destroy(engine);
    fs::remove_all(base);
    return 0;
}
