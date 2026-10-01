#include "kephir2/aur2.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace kephir2::aur2 {

ByteBuffer encode_stream_table(std::span<const StreamRecord> streams) {
    ByteBuffer out;
    put_varint(out, streams.size());

    std::unordered_set<std::uint64_t> ids;
    ids.reserve(streams.size());

    for (const auto& stream : streams) {
        if (stream.stream_id == 0) {
            throw std::runtime_error("AUR2 stream id zero is reserved");
        }
        if (!ids.insert(stream.stream_id).second) {
            throw std::runtime_error("duplicate AUR2 stream id");
        }
        if (stream.codec_id == 0) {
            throw std::runtime_error("AUR2 stream codec id cannot be zero");
        }
        if (stream.compressed_size == 0 || stream.raw_size == 0) {
            throw std::runtime_error("AUR2 non-empty stream must have non-zero sizes");
        }

        put_varint(out, stream.stream_id);
        put_varint(out, stream.payload_offset);
        put_varint(out, stream.compressed_size);
        put_varint(out, stream.raw_size);
        put_varint(out, stream.codec_id);
        put_varint(out, stream.codec_flags);
    }

    return out;
}

std::vector<StreamRecord> decode_stream_table(std::span<const std::uint8_t> data) {
    std::size_t pos = 0;
    const auto count = get_varint(data, pos);
    if (count > data.size()) {
        throw std::runtime_error("AUR2 stream count is not plausible");
    }

    std::vector<StreamRecord> streams;
    streams.reserve(static_cast<std::size_t>(count));
    std::unordered_set<std::uint64_t> ids;
    ids.reserve(static_cast<std::size_t>(count));

    for (std::uint64_t i = 0; i < count; ++i) {
        StreamRecord stream;
        stream.stream_id = get_varint(data, pos);
        stream.payload_offset = get_varint(data, pos);
        stream.compressed_size = get_varint(data, pos);
        stream.raw_size = get_varint(data, pos);

        const auto codec_id = get_varint(data, pos);
        if (codec_id > std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error("AUR2 stream codec id overflow");
        }
        stream.codec_id = static_cast<std::uint32_t>(codec_id);
        stream.codec_flags = get_varint(data, pos);

        if (stream.stream_id == 0) {
            throw std::runtime_error("AUR2 stream id zero is reserved");
        }
        if (!ids.insert(stream.stream_id).second) {
            throw std::runtime_error("duplicate AUR2 stream id");
        }
        if (stream.codec_id == 0) {
            throw std::runtime_error("AUR2 stream codec id cannot be zero");
        }
        if (stream.compressed_size == 0 || stream.raw_size == 0) {
            throw std::runtime_error("AUR2 non-empty stream must have non-zero sizes");
        }

        streams.push_back(stream);
    }

    if (pos != data.size()) {
        throw std::runtime_error("AUR2 stream table trailing bytes");
    }
    return streams;
}

void validate_container_structure(const Container& container) {
    const Section* file_table = nullptr;
    const Section* codec_descriptor = nullptr;
    const Section* stream_table = nullptr;
    const Section* data_section = nullptr;

    auto assign_unique = [](const Section*& slot, const Section& section, const char* name) {
        if (slot != nullptr) {
            throw std::runtime_error(std::string("duplicate AUR2 ") + name + " section");
        }
        slot = &section;
    };

    for (const auto& section : container.sections) {
        switch (static_cast<SectionType>(section.type)) {
            case SectionType::FileTable:
                assign_unique(file_table, section, "FILE_TABLE");
                break;
            case SectionType::CodecDescriptor:
                assign_unique(codec_descriptor, section, "CODEC_DESCRIPTOR");
                break;
            case SectionType::BlockTable:
                assign_unique(stream_table, section, "BLOCK_TABLE");
                break;
            case SectionType::Data:
                assign_unique(data_section, section, "DATA");
                break;
            default:
                break;
        }
    }

    if (file_table == nullptr || codec_descriptor == nullptr ||
        stream_table == nullptr || data_section == nullptr) {
        throw std::runtime_error("AUR2 complete archive requires FILE_TABLE, CODEC_DESCRIPTOR, BLOCK_TABLE and DATA");
    }

    const auto entries = decode_file_table(file_table->payload);
    const auto descriptor = decode_codec_descriptor(codec_descriptor->payload);
    auto streams = decode_stream_table(stream_table->payload);

    if (descriptor.codec_id == kCodecKephir &&
        (container.header.feature_flags & feature_bit(Feature::Kephir2)) == 0) {
        throw std::runtime_error("AUR2 KEPHIR archive is missing KEPHIR2 feature flag");
    }

    std::uint64_t logical_sum = 0;
    bool has_directory_entry = false;
    for (const auto& entry : entries) {
        if (entry.type == EntryType::Directory) {
            has_directory_entry = true;
        } else {
            if (entry.logical_size > std::numeric_limits<std::uint64_t>::max() - logical_sum) {
                throw std::runtime_error("AUR2 logical size overflow");
            }
            logical_sum += entry.logical_size;
        }
    }

    if (logical_sum != container.header.logical_size) {
        throw std::runtime_error("AUR2 header logical size does not match file table");
    }
    if (has_directory_entry &&
        (container.header.feature_flags & feature_bit(Feature::Directory)) == 0) {
        throw std::runtime_error("AUR2 directory entry requires DIRECTORY feature flag");
    }
    if (streams.size() > 1 &&
        (container.header.feature_flags & feature_bit(Feature::MultiStream)) == 0) {
        throw std::runtime_error("AUR2 multiple streams require MULTISTREAM feature flag");
    }

    std::sort(streams.begin(), streams.end(), [](const StreamRecord& a, const StreamRecord& b) {
        return a.payload_offset < b.payload_offset;
    });

    std::uint64_t expected_payload_offset = 0;
    std::unordered_map<std::uint64_t, StreamRecord> by_id;
    by_id.reserve(streams.size());

    for (const auto& stream : streams) {
        if (stream.codec_id != descriptor.codec_id) {
            throw std::runtime_error("AUR2 stream codec does not match codec descriptor");
        }
        if (stream.payload_offset != expected_payload_offset) {
            throw std::runtime_error("AUR2 v2.0 DATA streams must be contiguous and non-overlapping");
        }
        if (stream.compressed_size > std::numeric_limits<std::uint64_t>::max() - expected_payload_offset) {
            throw std::runtime_error("AUR2 DATA stream range overflow");
        }
        expected_payload_offset += stream.compressed_size;
        by_id.emplace(stream.stream_id, stream);
    }

    if (expected_payload_offset != data_section->payload.size()) {
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

        if (entry.stream_id == 0) {
            throw std::runtime_error("AUR2 non-empty file must reference a stream");
        }

        const auto it = by_id.find(entry.stream_id);
        if (it == by_id.end()) {
            throw std::runtime_error("AUR2 file references unknown stream");
        }
        const auto& stream = it->second;

        if (entry.stream_offset > stream.raw_size ||
            entry.logical_size > stream.raw_size - entry.stream_offset) {
            throw std::runtime_error("AUR2 file range exceeds decoded stream");
        }

        files_by_stream[entry.stream_id].push_back(&entry);
    }

    for (const auto& stream : streams) {
        auto it = files_by_stream.find(stream.stream_id);
        if (it == files_by_stream.end()) {
            throw std::runtime_error("AUR2 stream is not referenced by any file");
        }

        auto files = it->second;
        std::sort(files.begin(), files.end(), [](const FileEntry* a, const FileEntry* b) {
            if (a->stream_offset != b->stream_offset) {
                return a->stream_offset < b->stream_offset;
            }
            return a->entry_id < b->entry_id;
        });

        std::uint64_t raw_cursor = 0;
        for (const auto* file : files) {
            if (file->stream_offset != raw_cursor) {
                throw std::runtime_error("AUR2 file ranges leave a gap or overlap inside decoded stream");
            }
            if (file->logical_size > std::numeric_limits<std::uint64_t>::max() - raw_cursor) {
                throw std::runtime_error("AUR2 decoded stream file range overflow");
            }
            raw_cursor += file->logical_size;
        }

        if (raw_cursor != stream.raw_size) {
            throw std::runtime_error("AUR2 file ranges do not exactly cover decoded stream");
        }
    }
}

} // namespace kephir2::aur2
