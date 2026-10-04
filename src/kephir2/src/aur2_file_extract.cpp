#include "kephir2/aur2_file_extract.hpp"

#include "kephir2/archive.hpp"
#include "kephir2/aur2.hpp"
#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/aur2_progress.hpp"
#include "kephir2/aur2_ranged_file.hpp"
#include "kephir2/packing.hpp"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace kephir2::aur2 {
namespace {

std::uint32_t decode_backend_format_version(std::span<const std::uint8_t> data) {
    if (data.size() != 4) {
        throw std::runtime_error("unsupported AUR2 KEPHIR codec descriptor payload");
    }
    return static_cast<std::uint32_t>(data[0]) |
        (static_cast<std::uint32_t>(data[1]) << 8u) |
        (static_cast<std::uint32_t>(data[2]) << 16u) |
        (static_cast<std::uint32_t>(data[3]) << 24u);
}

void verify_descriptor(
    const CodecDescriptor& descriptor,
    const CompressionBackend& backend) {

    if (descriptor.codec_id != kCodecKephir) {
        throw std::runtime_error("AUR2 archive uses unsupported codec");
    }
    if (descriptor.codec_major != 2) {
        throw std::runtime_error("unsupported AUR2 KEPHIR codec major version");
    }
    if (decode_backend_format_version(descriptor.private_data)
        != backend.format_version()) {
        throw std::runtime_error("AUR2 KEPHIR backend format version mismatch");
    }
}

std::uint64_t sum_stream_units(std::span<const StreamRecord> streams) {
    std::uint64_t total = 0;
    for (const auto& stream : streams) {
        if (stream.raw_size > std::numeric_limits<std::uint64_t>::max() - total) {
            throw std::runtime_error("AUR2 extraction progress size overflow");
        }
        total += stream.raw_size;
    }
    return total;
}

} // namespace

void extract_indexed_file_backed(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options) {

    // Performs complete metadata/layout validation without reading DATA bytes.
    (void)inspect_indexed_file(archive);

    IndexedRangeReader reader(archive);
    const auto entries = decode_file_table(
        reader.read_section_payload(SectionType::FileTable));
    const auto descriptor = decode_codec_descriptor(
        reader.read_section_payload(SectionType::CodecDescriptor));
    auto streams = decode_stream_table(
        reader.read_section_payload(SectionType::BlockTable));
    verify_descriptor(descriptor, backend);

    std::unordered_map<std::uint64_t, std::uint32_t> expected_crc;
    if ((reader.header().feature_flags & feature_bit(Feature::Integrity)) != 0) {
        const auto integrity = decode_integrity_table(
            reader.read_section_payload(SectionType::Integrity));
        expected_crc.reserve(integrity.size());
        for (const auto& record : integrity) {
            if (!expected_crc.emplace(record.stream_id, record.payload_crc32).second) {
                throw std::runtime_error("duplicate AUR2 integrity stream id");
            }
        }
    }

    std::filesystem::create_directories(output_directory);

    // Create explicit directories first, including empty directories.
    for (const auto& entry : entries) {
        if (entry.type != EntryType::Directory) continue;
        std::filesystem::create_directories(
            safe_archive_target(output_directory, entry.path));
    }

    // PackedGroupSink derives logical offsets from record order, so preserve the
    // validated stream_offset ordering explicitly.
    std::vector<const FileEntry*> non_empty;
    non_empty.reserve(entries.size());
    for (const auto& entry : entries) {
        if (entry.type != EntryType::File) continue;

        if (entry.logical_size == 0 && entry.stream_id == 0) {
            const auto target = safe_archive_target(output_directory, entry.path);
            std::filesystem::create_directories(target.parent_path());
            std::ofstream out(target, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("unable to create empty file-backed AUR2 target");
            }
            continue;
        }
        non_empty.push_back(&entry);
    }

    std::sort(non_empty.begin(), non_empty.end(), [](const FileEntry* a, const FileEntry* b) {
        if (a->stream_id != b->stream_id) return a->stream_id < b->stream_id;
        if (a->stream_offset != b->stream_offset) return a->stream_offset < b->stream_offset;
        return a->entry_id < b->entry_id;
    });

    std::vector<ManifestRecord> records;
    records.reserve(non_empty.size());
    for (const auto* entry : non_empty) {
        records.push_back({entry->path, entry->stream_id, entry->logical_size});
    }

    std::sort(streams.begin(), streams.end(), [](const StreamRecord& a, const StreamRecord& b) {
        return a.stream_id < b.stream_id;
    });

    const auto total_units = sum_stream_units(streams);
    std::uint64_t completed_units = 0;

    for (const auto& stream : streams) {
        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        // The only compressed payload resident in memory is the current stream.
        auto blob = reader.read_section_range(
            SectionType::Data,
            stream.payload_offset,
            stream.compressed_size);

        if (!expected_crc.empty()) {
            const auto it = expected_crc.find(stream.stream_id);
            if (it == expected_crc.end()) {
                throw std::runtime_error("AUR2 integrity table does not cover stream");
            }
            if (crc32(blob) != it->second) {
                throw std::runtime_error("AUR2 stream payload CRC32 mismatch");
            }
        }

        PackedGroupSink sink(
            output_directory,
            records,
            stream.stream_id,
            stream.raw_size);

        StreamProgressAdapter progress(
            options,
            completed_units,
            stream.raw_size,
            total_units);
        const auto stream_options = progress.options(options);

        const auto stats = backend.decode(
            blob,
            stream.raw_size,
            sink,
            stream_options);
        if (stats.output_bytes != 0 && stats.output_bytes != stream.raw_size) {
            throw std::runtime_error("backend reported inconsistent file-backed output length");
        }
        if (sink.size() != stream.raw_size) {
            throw std::runtime_error("file-backed AUR2 decoded stream size mismatch");
        }

        if (stream.raw_size > std::numeric_limits<std::uint64_t>::max() - completed_units) {
            throw std::runtime_error("AUR2 extraction progress accumulation overflow");
        }
        completed_units += stream.raw_size;

        // Explicit release before moving to the next stream.
        blob.clear();
        blob.shrink_to_fit();
    }

    // Final exact output verification. Metadata restoration is deliberately a
    // separate layer and is not performed by this internal extractor yet.
    for (const auto& entry : entries) {
        const auto target = safe_archive_target(output_directory, entry.path);
        if (entry.type == EntryType::Directory) {
            if (!std::filesystem::is_directory(target)) {
                throw std::runtime_error("file-backed AUR2 directory verification failed");
            }
        } else if (!std::filesystem::is_regular_file(target)
                   || std::filesystem::file_size(target) != entry.logical_size) {
            throw std::runtime_error("file-backed AUR2 file verification failed");
        }
    }
}

} // namespace kephir2::aur2
