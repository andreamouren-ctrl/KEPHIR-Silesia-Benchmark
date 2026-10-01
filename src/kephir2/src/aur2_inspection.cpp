#include "kephir2/aur2_inspection.hpp"

#include <algorithm>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kephir2::aur2 {
namespace {

const Section& find_required_section(const Container& container, SectionType type) {
    const auto raw = static_cast<std::uint32_t>(type);
    const Section* found = nullptr;
    for (const auto& section : container.sections) {
        if (section.type != raw) continue;
        if (found != nullptr) {
            throw std::runtime_error("duplicate required AUR2 section");
        }
        found = &section;
    }
    if (found == nullptr) {
        throw std::runtime_error("missing required AUR2 section");
    }
    return *found;
}

bool has_section(const Container& container, SectionType type) noexcept {
    const auto raw = static_cast<std::uint32_t>(type);
    return std::any_of(
        container.sections.begin(),
        container.sections.end(),
        [raw](const Section& section) { return section.type == raw; });
}

std::uint32_t decode_backend_format_version(std::span<const std::uint8_t> data) {
    if (data.size() != 4) {
        throw std::runtime_error("unsupported AUR2 KEPHIR codec descriptor payload");
    }
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8u) |
           (static_cast<std::uint32_t>(data[2]) << 16u) |
           (static_cast<std::uint32_t>(data[3]) << 24u);
}

class CoverageSink final : public ByteSink {
public:
    explicit CoverageSink(std::uint64_t expected)
        : expected_(expected) {}

    void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) override {

        if (source.empty()) {
            if (offset > expected_) {
                throw std::out_of_range("AUR2 test sink offset out of range");
            }
            return;
        }

        if (offset >= expected_ || source.size() > expected_ - offset) {
            throw std::out_of_range("AUR2 test sink write exceeds raw stream size");
        }

        const auto end = offset + static_cast<std::uint64_t>(source.size());
        ranges_.push_back({offset, end});
    }

    [[nodiscard]] bool complete() {
        if (expected_ == 0) return ranges_.empty();
        if (ranges_.empty()) return false;

        std::sort(ranges_.begin(), ranges_.end());
        std::uint64_t covered_end = 0;

        for (const auto& range : ranges_) {
            if (range.first > covered_end) {
                return false;
            }
            if (range.first < covered_end) {
                throw std::runtime_error("AUR2 backend wrote overlapping decoded ranges");
            }
            covered_end = range.second;
        }

        return covered_end == expected_;
    }

private:
    std::uint64_t expected_{0};
    std::vector<std::pair<std::uint64_t, std::uint64_t>> ranges_;
};

} // namespace

ArchiveInfo inspect_archive(std::span<const std::uint8_t> archive) {
    const auto container = decode_container(archive);
    validate_container_structure(container);

    const auto entries = decode_file_table(
        find_required_section(container, SectionType::FileTable).payload);
    const auto streams = decode_stream_table(
        find_required_section(container, SectionType::BlockTable).payload);
    const auto descriptor = decode_codec_descriptor(
        find_required_section(container, SectionType::CodecDescriptor).payload);

    ArchiveInfo info;
    info.container_major = container.header.container_major;
    info.container_minor = container.header.container_minor;
    info.codec_major = descriptor.codec_major;
    info.codec_minor = descriptor.codec_minor;
    info.feature_flags = container.header.feature_flags;
    info.entry_count = entries.size();
    info.logical_bytes = container.header.logical_size;
    info.archive_bytes = archive.size();
    info.stream_count = streams.size();
    info.is_encrypted =
        (container.header.feature_flags & feature_bit(Feature::Encryption)) != 0;
    info.integrity_available =
        has_section(container, SectionType::Integrity) ||
        (container.header.feature_flags & feature_bit(Feature::Integrity)) != 0;
    return info;
}

std::vector<FileEntry> list_entries(std::span<const std::uint8_t> archive) {
    const auto container = decode_container(archive);
    validate_container_structure(container);
    return decode_file_table(
        find_required_section(container, SectionType::FileTable).payload);
}

void test_archive(
    std::span<const std::uint8_t> archive,
    CompressionBackend& backend,
    const BackendOptions& options) {

    const auto container = decode_container(archive);
    validate_container_structure(container);

    const auto descriptor = decode_codec_descriptor(
        find_required_section(container, SectionType::CodecDescriptor).payload);
    if (descriptor.codec_id != kCodecKephir) {
        throw std::runtime_error("AUR2 archive uses unsupported codec");
    }

    const auto required_backend_format =
        decode_backend_format_version(descriptor.private_data);
    if (required_backend_format != backend.format_version()) {
        throw std::runtime_error("AUR2 KEPHIR backend format version mismatch");
    }

    const auto streams = decode_stream_table(
        find_required_section(container, SectionType::BlockTable).payload);
    const auto& data = find_required_section(container, SectionType::Data).payload;

    for (const auto& stream : streams) {
        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        if (stream.payload_offset > data.size() ||
            stream.compressed_size > data.size() - stream.payload_offset) {
            throw std::runtime_error("AUR2 compressed stream range exceeds DATA section");
        }
        if (stream.compressed_size > std::numeric_limits<std::size_t>::max()) {
            throw std::runtime_error("AUR2 compressed stream is too large for this process");
        }

        const auto begin = static_cast<std::size_t>(stream.payload_offset);
        const auto size = static_cast<std::size_t>(stream.compressed_size);
        const auto blob = std::span<const std::uint8_t>(data.data() + begin, size);

        CoverageSink sink(stream.raw_size);
        const auto stats = backend.decode(
            blob,
            stream.raw_size,
            sink,
            options);

        if (stats.output_bytes != 0 && stats.output_bytes != stream.raw_size) {
            throw std::runtime_error("backend reported inconsistent AUR2 test output length");
        }
        if (!sink.complete()) {
            throw std::runtime_error("AUR2 test decode did not cover complete raw stream");
        }
    }
}

} // namespace kephir2::aur2
