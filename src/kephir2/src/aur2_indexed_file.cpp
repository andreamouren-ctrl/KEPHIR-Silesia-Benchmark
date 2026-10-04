#include "kephir2/aur2_indexed_file.hpp"

#include "kephir2/aur2_seek.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace kephir2::aur2 {
namespace {

constexpr std::uint64_t kMaxSeekPayloadBytes = 16ull * 1024ull * 1024ull;

struct SectionHeaderView {
    std::uint32_t type{0};
    std::uint32_t flags{0};
    std::uint64_t payload_size{0};
};

struct IndexedContext {
    Header header{};
    std::uint64_t archive_size{0};
    std::vector<SeekIndexRecord> records;
};

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated indexed AUR2 uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated indexed AUR2 uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a) {
        throw std::runtime_error("indexed AUR2 offset overflow");
    }
    return a + b;
}

ByteBuffer read_exact(
    const std::filesystem::path& path,
    std::uint64_t offset,
    std::uint64_t size,
    std::uint64_t archive_size) {

    if (offset > archive_size || size > archive_size - offset) {
        throw std::runtime_error("indexed AUR2 read range exceeds archive");
    }
    if (size > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("indexed AUR2 read range exceeds address space");
    }
    if (offset > static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) {
        throw std::runtime_error("indexed AUR2 offset exceeds stream range");
    }

    ByteBuffer out(static_cast<std::size_t>(size));
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to open indexed AUR2 archive");
    }
    in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("unable to seek indexed AUR2 archive");
    }
    if (!out.empty()) {
        in.read(
            reinterpret_cast<char*>(out.data()),
            static_cast<std::streamsize>(out.size()));
        if (in.gcount() != static_cast<std::streamsize>(out.size())) {
            throw std::runtime_error("short read from indexed AUR2 archive");
        }
    }
    return out;
}

SectionHeaderView read_section_header(
    const std::filesystem::path& path,
    std::uint64_t offset,
    std::uint64_t archive_size) {

    const auto raw = read_exact(path, offset, kSectionHeaderSize, archive_size);
    SectionHeaderView header;
    header.type = read_u32(raw, 0);
    header.flags = read_u32(raw, 4);
    header.payload_size = read_u64(raw, 8);
    return header;
}

IndexedContext load_indexed_context(const std::filesystem::path& path) {
    IndexedContext ctx;
    ctx.archive_size = std::filesystem::file_size(path);
    if (ctx.archive_size < kFixedHeaderSize) {
        throw std::runtime_error("truncated AUR2 fixed header");
    }

    const auto raw_header = read_exact(path, 0, kFixedHeaderSize, ctx.archive_size);
    ctx.header = decode_header(raw_header);

    if ((ctx.header.feature_flags & feature_bit(Feature::SeekIndex)) == 0) {
        throw std::runtime_error("AUR2 seek index unavailable");
    }
    if (ctx.header.toc_offset != ctx.header.header_size) {
        throw std::runtime_error("AUR2 SEEK_INDEX is not located at TOC offset");
    }

    const auto seek_header = read_section_header(
        path,
        ctx.header.toc_offset,
        ctx.archive_size);
    if (seek_header.type != static_cast<std::uint32_t>(SectionType::SeekIndex)) {
        throw std::runtime_error("AUR2 TOC does not reference SEEK_INDEX");
    }
    if (seek_header.payload_size > kMaxSeekPayloadBytes) {
        throw std::runtime_error("AUR2 seek-index payload exceeds safety bound");
    }

    const auto seek_payload_offset = checked_add(
        ctx.header.toc_offset,
        kSectionHeaderSize);
    const auto seek_payload = read_exact(
        path,
        seek_payload_offset,
        seek_header.payload_size,
        ctx.archive_size);
    ctx.records = decode_seek_index(seek_payload);

    std::uint64_t cursor = checked_add(
        seek_payload_offset,
        seek_header.payload_size);

    for (const auto& record : ctx.records) {
        if (record.section_offset != cursor) {
            throw std::runtime_error("AUR2 seek-index section offset mismatch");
        }
        if (record.payload_offset != checked_add(cursor, kSectionHeaderSize)) {
            throw std::runtime_error("AUR2 seek-index payload offset mismatch");
        }

        const auto actual = read_section_header(path, cursor, ctx.archive_size);
        if (actual.type != record.section_type ||
            actual.flags != record.section_flags ||
            actual.payload_size != record.payload_size) {
            throw std::runtime_error("AUR2 seek-index record disagrees with section header");
        }

        cursor = checked_add(record.payload_offset, record.payload_size);
        if (cursor > ctx.archive_size) {
            throw std::runtime_error("AUR2 seek-index section exceeds archive");
        }
    }

    if (cursor != ctx.archive_size) {
        throw std::runtime_error("AUR2 seek-index does not cover complete archive layout");
    }
    return ctx;
}

const SeekIndexRecord& require_record(
    const IndexedContext& ctx,
    SectionType type) {

    const auto raw = static_cast<std::uint32_t>(type);
    const SeekIndexRecord* found = nullptr;
    for (const auto& record : ctx.records) {
        if (record.section_type != raw) continue;
        if (found) {
            throw std::runtime_error("duplicate indexed AUR2 section");
        }
        found = &record;
    }
    if (!found) {
        throw std::runtime_error("missing required indexed AUR2 section");
    }
    return *found;
}

const SeekIndexRecord* optional_record(
    const IndexedContext& ctx,
    SectionType type) {

    const auto raw = static_cast<std::uint32_t>(type);
    const SeekIndexRecord* found = nullptr;
    for (const auto& record : ctx.records) {
        if (record.section_type != raw) continue;
        if (found) {
            throw std::runtime_error("duplicate indexed AUR2 section");
        }
        found = &record;
    }
    return found;
}

ByteBuffer read_record_payload(
    const std::filesystem::path& path,
    const IndexedContext& ctx,
    const SeekIndexRecord& record) {

    return read_exact(
        path,
        record.payload_offset,
        record.payload_size,
        ctx.archive_size);
}

void validate_metadata_structure(
    const IndexedContext& ctx,
    const std::vector<FileEntry>& entries,
    const CodecDescriptor& descriptor,
    std::vector<StreamRecord> streams,
    const SeekIndexRecord& data_record,
    const std::vector<IntegrityRecord>* integrity) {

    if (descriptor.codec_id == kCodecKephir &&
        (ctx.header.feature_flags & feature_bit(Feature::Kephir2)) == 0) {
        throw std::runtime_error("AUR2 KEPHIR archive is missing KEPHIR2 feature flag");
    }

    std::uint64_t logical_sum = 0;
    bool has_directory = false;
    for (const auto& entry : entries) {
        if (entry.type == EntryType::Directory) {
            has_directory = true;
            continue;
        }
        logical_sum = checked_add(logical_sum, entry.logical_size);
    }
    if (logical_sum != ctx.header.logical_size) {
        throw std::runtime_error("AUR2 header logical size does not match file table");
    }
    if (has_directory &&
        (ctx.header.feature_flags & feature_bit(Feature::Directory)) == 0) {
        throw std::runtime_error("AUR2 directory entry requires DIRECTORY feature flag");
    }
    if (streams.size() > 1 &&
        (ctx.header.feature_flags & feature_bit(Feature::MultiStream)) == 0) {
        throw std::runtime_error("AUR2 multiple streams require MULTISTREAM feature flag");
    }

    std::sort(streams.begin(), streams.end(), [](const auto& a, const auto& b) {
        return a.payload_offset < b.payload_offset;
    });

    std::uint64_t compressed_cursor = 0;
    std::unordered_map<std::uint64_t, StreamRecord> by_id;
    by_id.reserve(streams.size());
    for (const auto& stream : streams) {
        if (stream.codec_id != descriptor.codec_id) {
            throw std::runtime_error("AUR2 stream codec does not match codec descriptor");
        }
        if (stream.payload_offset != compressed_cursor) {
            throw std::runtime_error("AUR2 DATA streams must be contiguous and non-overlapping");
        }
        compressed_cursor = checked_add(compressed_cursor, stream.compressed_size);
        if (!by_id.emplace(stream.stream_id, stream).second) {
            throw std::runtime_error("duplicate AUR2 stream id");
        }
    }
    if (compressed_cursor != data_record.payload_size) {
        throw std::runtime_error("AUR2 DATA payload size does not match stream table");
    }

    std::unordered_map<std::uint64_t, std::vector<const FileEntry*>> files_by_stream;
    files_by_stream.reserve(streams.size());
    for (const auto& entry : entries) {
        if (entry.type == EntryType::Directory) {
            if (entry.stream_id != 0 || entry.stream_offset != 0) {
                throw std::runtime_error("AUR2 directory entry cannot reference a stream");
            }
            continue;
        }
        if (entry.logical_size == 0 && entry.stream_id == 0) {
            if (entry.stream_offset != 0) {
                throw std::runtime_error("AUR2 empty file without stream must have zero stream offset");
            }
            continue;
        }
        const auto it = by_id.find(entry.stream_id);
        if (it == by_id.end()) {
            throw std::runtime_error("AUR2 file references unknown stream");
        }
        if (entry.stream_offset > it->second.raw_size ||
            entry.logical_size > it->second.raw_size - entry.stream_offset) {
            throw std::runtime_error("AUR2 file range exceeds decoded stream");
        }
        files_by_stream[entry.stream_id].push_back(&entry);
    }

    for (const auto& stream : streams) {
        const auto it = files_by_stream.find(stream.stream_id);
        if (it == files_by_stream.end()) {
            throw std::runtime_error("AUR2 stream is not referenced by any file");
        }
        auto files = it->second;
        std::sort(files.begin(), files.end(), [](const auto* a, const auto* b) {
            return a->stream_offset < b->stream_offset;
        });
        std::uint64_t raw_cursor = 0;
        for (const auto* file : files) {
            if (file->stream_offset != raw_cursor) {
                throw std::runtime_error("AUR2 file ranges leave a gap or overlap inside decoded stream");
            }
            raw_cursor = checked_add(raw_cursor, file->logical_size);
        }
        if (raw_cursor != stream.raw_size) {
            throw std::runtime_error("AUR2 file ranges do not exactly cover decoded stream");
        }
    }

    const bool integrity_flag =
        (ctx.header.feature_flags & feature_bit(Feature::Integrity)) != 0;
    if (integrity_flag != (integrity != nullptr)) {
        throw std::runtime_error("AUR2 INTEGRITY feature flag/section mismatch");
    }
    if (integrity) {
        if (integrity->size() != streams.size()) {
            throw std::runtime_error("AUR2 integrity table does not cover every stream");
        }
        std::unordered_set<std::uint64_t> ids;
        ids.reserve(integrity->size());
        for (const auto& record : *integrity) {
            if (by_id.find(record.stream_id) == by_id.end() ||
                !ids.insert(record.stream_id).second) {
                throw std::runtime_error("AUR2 integrity table references wrong stream set");
            }
        }
    }
}

} // namespace

bool has_seek_index_file(const std::filesystem::path& archive) {
    const auto size = std::filesystem::file_size(archive);
    if (size < kFixedHeaderSize) {
        throw std::runtime_error("truncated AUR2 fixed header");
    }
    const auto raw = read_exact(archive, 0, kFixedHeaderSize, size);
    const auto header = decode_header(raw);
    return (header.feature_flags & feature_bit(Feature::SeekIndex)) != 0;
}

ArchiveInfo inspect_indexed_file(const std::filesystem::path& archive) {
    const auto ctx = load_indexed_context(archive);

    const auto& file_record = require_record(ctx, SectionType::FileTable);
    const auto& codec_record = require_record(ctx, SectionType::CodecDescriptor);
    const auto& block_record = require_record(ctx, SectionType::BlockTable);
    const auto& data_record = require_record(ctx, SectionType::Data);

    const auto entries = decode_file_table(
        read_record_payload(archive, ctx, file_record));
    const auto descriptor = decode_codec_descriptor(
        read_record_payload(archive, ctx, codec_record));
    const auto streams = decode_stream_table(
        read_record_payload(archive, ctx, block_record));

    std::vector<IntegrityRecord> integrity_records;
    const auto* integrity_record = optional_record(ctx, SectionType::Integrity);
    const std::vector<IntegrityRecord>* integrity_ptr = nullptr;
    if (integrity_record) {
        integrity_records = decode_integrity_table(
            read_record_payload(archive, ctx, *integrity_record));
        integrity_ptr = &integrity_records;
    }

    validate_metadata_structure(
        ctx,
        entries,
        descriptor,
        streams,
        data_record,
        integrity_ptr);

    ArchiveInfo info;
    info.container_major = ctx.header.container_major;
    info.container_minor = ctx.header.container_minor;
    info.codec_major = descriptor.codec_major;
    info.codec_minor = descriptor.codec_minor;
    info.feature_flags = ctx.header.feature_flags;
    info.entry_count = entries.size();
    info.logical_bytes = ctx.header.logical_size;
    info.archive_bytes = ctx.archive_size;
    info.stream_count = streams.size();
    info.is_encrypted =
        (ctx.header.feature_flags & feature_bit(Feature::Encryption)) != 0;
    info.integrity_available = integrity_record != nullptr;
    return info;
}

std::vector<FileEntry> list_indexed_file(const std::filesystem::path& archive) {
    const auto ctx = load_indexed_context(archive);
    return decode_file_table(read_record_payload(
        archive,
        ctx,
        require_record(ctx, SectionType::FileTable)));
}

void validate_seek_index_file(const std::filesystem::path& archive) {
    (void)load_indexed_context(archive);
}

} // namespace kephir2::aur2
