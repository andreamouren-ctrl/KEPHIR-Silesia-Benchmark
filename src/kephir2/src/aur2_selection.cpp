#include "kephir2/aur2_selection.hpp"

#include "kephir2/archive.hpp"
#include "kephir2/aur2.hpp"
#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/aur2_progress.hpp"
#include "kephir2/aur2_ranged_file.hpp"

#include <algorithm>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
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

void verify_kephir_descriptor(
    const Container& container,
    const CompressionBackend& backend) {

    verify_descriptor(
        decode_codec_descriptor(
            find_required_section(container, SectionType::CodecDescriptor).payload),
        backend);
}

std::span<const std::uint8_t> stream_blob(
    const Section& data,
    const StreamRecord& stream) {

    if (stream.payload_offset > data.payload.size() ||
        stream.compressed_size > data.payload.size() - stream.payload_offset) {
        throw std::runtime_error("AUR2 compressed stream range exceeds DATA section");
    }

    const auto begin = static_cast<std::size_t>(stream.payload_offset);
    const auto size = static_cast<std::size_t>(stream.compressed_size);
    return {data.payload.data() + begin, size};
}

class SelectiveStreamSink final : public ByteSink {
public:
    struct Segment {
        std::filesystem::path target;
        std::uint64_t offset{0};
        std::uint64_t size{0};
    };

    SelectiveStreamSink(
        std::filesystem::path root,
        std::uint64_t raw_size,
        std::span<const FileEntry* const> selected)
        : raw_size_(raw_size) {

        segments_.reserve(selected.size());
        for (const auto* entry : selected) {
            if (!entry || entry->type != EntryType::File || entry->stream_id == 0) {
                throw std::runtime_error("invalid AUR2 selective stream entry");
            }
            if (entry->stream_offset > raw_size_ ||
                entry->logical_size > raw_size_ - entry->stream_offset) {
                throw std::runtime_error("AUR2 selective file range exceeds stream");
            }

            const auto target = safe_archive_target(root, entry->path);
            std::filesystem::create_directories(target.parent_path());
            {
                std::ofstream out(target, std::ios::binary | std::ios::trunc);
                if (!out) {
                    throw std::runtime_error("unable to create selective extraction target");
                }
            }
            std::error_code ec;
            std::filesystem::resize_file(target, entry->logical_size, ec);
            if (ec) {
                throw std::runtime_error("unable to size selective extraction target");
            }

            segments_.push_back({
                target,
                entry->stream_offset,
                entry->logical_size
            });
        }
    }

    void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) override {

        if (source.empty()) {
            if (offset > raw_size_) {
                throw std::out_of_range("selective stream sink offset out of range");
            }
            return;
        }
        if (offset >= raw_size_ || source.size() > raw_size_ - offset) {
            throw std::out_of_range("selective stream sink write exceeds stream");
        }

        const auto request_end = offset + source.size();
        for (const auto& segment : segments_) {
            const auto segment_end = segment.offset + segment.size;
            if (segment_end <= offset || segment.offset >= request_end) {
                continue;
            }

            const auto write_begin = std::max(offset, segment.offset);
            const auto write_end = std::min(request_end, segment_end);
            if (write_end <= write_begin) continue;

            const auto source_offset = static_cast<std::size_t>(write_begin - offset);
            const auto file_offset = write_begin - segment.offset;
            const auto bytes = static_cast<std::size_t>(write_end - write_begin);

            std::fstream out(
                segment.target,
                std::ios::binary | std::ios::in | std::ios::out);
            if (!out) {
                throw std::runtime_error("unable to open selective extraction target");
            }
            out.seekp(static_cast<std::streamoff>(file_offset), std::ios::beg);
            if (!out) {
                throw std::runtime_error("unable to seek selective extraction target");
            }
            out.write(
                reinterpret_cast<const char*>(source.data() + source_offset),
                static_cast<std::streamsize>(bytes));
            if (!out) {
                throw std::runtime_error("unable to write selective extraction target");
            }
        }
    }

private:
    std::uint64_t raw_size_{0};
    std::vector<Segment> segments_;
};

std::unordered_set<std::uint64_t> validate_selection(
    std::span<const std::uint64_t> entry_ids,
    const std::unordered_map<std::uint64_t, const FileEntry*>& by_entry_id) {

    std::unordered_set<std::uint64_t> selected_ids;
    selected_ids.reserve(entry_ids.size());
    for (const auto id : entry_ids) {
        if (!selected_ids.insert(id).second) {
            continue;
        }
        if (by_entry_id.find(id) == by_entry_id.end()) {
            throw std::invalid_argument("AUR2 selected entry id does not exist");
        }
    }
    return selected_ids;
}

std::unordered_map<std::uint64_t, std::vector<const FileEntry*>> prepare_selected_targets(
    const std::filesystem::path& output_directory,
    const std::unordered_set<std::uint64_t>& selected_ids,
    const std::unordered_map<std::uint64_t, const FileEntry*>& by_entry_id) {

    std::filesystem::create_directories(output_directory);

    std::unordered_map<std::uint64_t, std::vector<const FileEntry*>> selected_by_stream;
    for (const auto id : selected_ids) {
        const auto& entry = *by_entry_id.at(id);

        if (entry.type == EntryType::Directory) {
            std::filesystem::create_directories(
                safe_archive_target(output_directory, entry.path));
            continue;
        }

        if (entry.stream_id == 0) {
            if (entry.logical_size != 0) {
                throw std::runtime_error("AUR2 non-empty selected file has no stream");
            }
            const auto target = safe_archive_target(output_directory, entry.path);
            std::filesystem::create_directories(target.parent_path());
            std::ofstream out(target, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("unable to create selected empty file");
            }
            continue;
        }

        selected_by_stream[entry.stream_id].push_back(&entry);
    }
    return selected_by_stream;
}

std::uint64_t selected_stream_units(
    std::span<const FileEntry* const> selected) {

    std::uint64_t units = 0;
    for (const auto* entry : selected) {
        if (!entry) continue;
        if (entry->logical_size > std::numeric_limits<std::uint64_t>::max() - units) {
            throw std::runtime_error("AUR2 selective progress size overflow");
        }
        units += entry->logical_size;
    }
    return units;
}

std::uint64_t selected_total_units(
    const std::unordered_map<std::uint64_t, std::vector<const FileEntry*>>& selected_by_stream) {

    std::uint64_t total = 0;
    for (const auto& [stream_id, selected] : selected_by_stream) {
        (void)stream_id;
        const auto units = selected_stream_units(
            std::span<const FileEntry* const>(selected.data(), selected.size()));
        if (units > std::numeric_limits<std::uint64_t>::max() - total) {
            throw std::runtime_error("AUR2 selective progress total overflow");
        }
        total += units;
    }
    return total;
}

void verify_selected_outputs(
    const std::filesystem::path& output_directory,
    const std::unordered_set<std::uint64_t>& selected_ids,
    const std::unordered_map<std::uint64_t, const FileEntry*>& by_entry_id) {

    for (const auto id : selected_ids) {
        const auto& entry = *by_entry_id.at(id);
        const auto target = safe_archive_target(output_directory, entry.path);
        if (entry.type == EntryType::Directory) {
            if (!std::filesystem::is_directory(target)) {
                throw std::runtime_error("selected directory extraction verification failed");
            }
        } else if (!std::filesystem::is_regular_file(target)
                   || std::filesystem::file_size(target) != entry.logical_size) {
            throw std::runtime_error("selected file extraction verification failed");
        }
    }
}

} // namespace

void extract_selected(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    std::span<const std::uint64_t> entry_ids,
    const BackendOptions& options) {

    const auto container = decode_container(archive);
    validate_container_structure(container);
    verify_kephir_descriptor(container, backend);

    const auto entries = decode_file_table(
        find_required_section(container, SectionType::FileTable).payload);
    const auto streams = decode_stream_table(
        find_required_section(container, SectionType::BlockTable).payload);
    const auto& data = find_required_section(container, SectionType::Data);

    std::unordered_map<std::uint64_t, const FileEntry*> by_entry_id;
    by_entry_id.reserve(entries.size());
    for (const auto& entry : entries) {
        by_entry_id.emplace(entry.entry_id, &entry);
    }

    const auto selected_ids = validate_selection(entry_ids, by_entry_id);
    const auto selected_by_stream = prepare_selected_targets(
        output_directory,
        selected_ids,
        by_entry_id);
    const auto total_units = selected_total_units(selected_by_stream);
    std::uint64_t completed_units = 0;

    for (const auto& stream : streams) {
        const auto selected_it = selected_by_stream.find(stream.stream_id);
        if (selected_it == selected_by_stream.end()) {
            continue;
        }

        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        const auto& selected = selected_it->second;
        SelectiveStreamSink sink(
            output_directory,
            stream.raw_size,
            std::span<const FileEntry* const>(selected.data(), selected.size()));

        const auto stream_units = selected_stream_units(
            std::span<const FileEntry* const>(selected.data(), selected.size()));
        StreamProgressAdapter progress(
            options,
            completed_units,
            stream_units,
            total_units);
        const auto stream_options = progress.options(options);

        const auto stats = backend.decode(
            stream_blob(data, stream),
            stream.raw_size,
            sink,
            stream_options);
        if (stats.output_bytes != 0 && stats.output_bytes != stream.raw_size) {
            throw std::runtime_error("backend reported inconsistent selective decode length");
        }
        if (stream_units > std::numeric_limits<std::uint64_t>::max() - completed_units) {
            throw std::runtime_error("AUR2 selective progress accumulation overflow");
        }
        completed_units += stream_units;
    }

    verify_selected_outputs(output_directory, selected_ids, by_entry_id);
}

void extract_selected_indexed_file_backed(
    const std::filesystem::path& archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    std::span<const std::uint64_t> entry_ids,
    const BackendOptions& options) {

    // Validate all metadata/layout relationships without loading DATA.
    (void)inspect_indexed_file(archive);

    IndexedRangeReader reader(archive);
    const auto entries = decode_file_table(
        reader.read_section_payload(SectionType::FileTable));
    const auto descriptor = decode_codec_descriptor(
        reader.read_section_payload(SectionType::CodecDescriptor));
    const auto streams = decode_stream_table(
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

    std::unordered_map<std::uint64_t, const FileEntry*> by_entry_id;
    by_entry_id.reserve(entries.size());
    for (const auto& entry : entries) {
        by_entry_id.emplace(entry.entry_id, &entry);
    }

    const auto selected_ids = validate_selection(entry_ids, by_entry_id);
    const auto selected_by_stream = prepare_selected_targets(
        output_directory,
        selected_ids,
        by_entry_id);
    const auto total_units = selected_total_units(selected_by_stream);
    std::uint64_t completed_units = 0;

    for (const auto& stream : streams) {
        const auto selected_it = selected_by_stream.find(stream.stream_id);
        if (selected_it == selected_by_stream.end()) {
            continue;
        }

        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        auto blob = reader.read_section_range(
            SectionType::Data,
            stream.payload_offset,
            stream.compressed_size);

        if (!expected_crc.empty()) {
            const auto crc_it = expected_crc.find(stream.stream_id);
            if (crc_it == expected_crc.end()) {
                throw std::runtime_error("AUR2 integrity table does not cover selected stream");
            }
            if (crc32(blob) != crc_it->second) {
                throw std::runtime_error("AUR2 selected stream payload CRC32 mismatch");
            }
        }

        const auto& selected = selected_it->second;
        SelectiveStreamSink sink(
            output_directory,
            stream.raw_size,
            std::span<const FileEntry* const>(selected.data(), selected.size()));

        const auto stream_units = selected_stream_units(
            std::span<const FileEntry* const>(selected.data(), selected.size()));
        StreamProgressAdapter progress(
            options,
            completed_units,
            stream_units,
            total_units);
        const auto stream_options = progress.options(options);

        const auto stats = backend.decode(
            blob,
            stream.raw_size,
            sink,
            stream_options);
        if (stats.output_bytes != 0 && stats.output_bytes != stream.raw_size) {
            throw std::runtime_error("backend reported inconsistent file-backed selective decode length");
        }
        if (stream_units > std::numeric_limits<std::uint64_t>::max() - completed_units) {
            throw std::runtime_error("AUR2 selective progress accumulation overflow");
        }
        completed_units += stream_units;

        blob.clear();
        blob.shrink_to_fit();
    }

    verify_selected_outputs(output_directory, selected_ids, by_entry_id);
}

} // namespace kephir2::aur2
