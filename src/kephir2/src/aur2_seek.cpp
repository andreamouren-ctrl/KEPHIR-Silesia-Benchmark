#include "kephir2/aur2_seek.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#include <vector>

namespace kephir2::aur2 {
namespace {

constexpr std::array<std::uint8_t, 4> kSeekMagic{'S', 'I', 'X', '1'};
constexpr std::size_t kSeekHeaderSize = 16;
constexpr std::size_t kSeekTrailerSize = 4;

void append_u16(ByteBuffer& out, std::uint16_t value) {
    out.push_back(static_cast<std::uint8_t>(value & 0xffu));
    out.push_back(static_cast<std::uint8_t>((value >> 8u) & 0xffu));
}

void append_u32(ByteBuffer& out, std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<std::uint8_t>((value >> shift) & 0xffu));
    }
}

void append_u64(ByteBuffer& out, std::uint64_t value) {
    for (unsigned shift = 0; shift < 64; shift += 8) {
        out.push_back(static_cast<std::uint8_t>((value >> shift) & 0xffu));
    }
}

std::uint16_t read_u16(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 2) {
        throw std::runtime_error("truncated AUR2 seek-index uint16");
    }
    return static_cast<std::uint16_t>(data[offset]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[offset + 1]) << 8u);
}

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated AUR2 seek-index uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated AUR2 seek-index uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a) {
        throw std::runtime_error("AUR2 seek-index offset overflow");
    }
    return a + b;
}

} // namespace

ByteBuffer encode_seek_index(std::span<const SeekIndexRecord> records) {
    const auto max_count =
        (std::numeric_limits<std::size_t>::max() - kSeekHeaderSize - kSeekTrailerSize)
        / kSeekIndexRecordSize;
    if (records.size() > max_count) {
        throw std::runtime_error("AUR2 seek-index record count is too large");
    }

    ByteBuffer out;
    out.reserve(
        kSeekHeaderSize
        + records.size() * kSeekIndexRecordSize
        + kSeekTrailerSize);
    out.insert(out.end(), kSeekMagic.begin(), kSeekMagic.end());
    append_u16(out, kSeekIndexVersion);
    append_u16(out, kSeekIndexRecordSize);
    append_u64(out, static_cast<std::uint64_t>(records.size()));

    for (const auto& record : records) {
        if (record.section_type == static_cast<std::uint32_t>(SectionType::SeekIndex)) {
            throw std::runtime_error("AUR2 seek-index cannot index itself");
        }
        if (record.payload_offset != checked_add(record.section_offset, kSectionHeaderSize)) {
            throw std::runtime_error("AUR2 seek-index payload offset mismatch");
        }
        append_u32(out, record.section_type);
        append_u32(out, record.section_flags);
        append_u64(out, record.section_offset);
        append_u64(out, record.payload_offset);
        append_u64(out, record.payload_size);
    }

    append_u32(out, crc32(out));
    return out;
}

std::vector<SeekIndexRecord> decode_seek_index(
    std::span<const std::uint8_t> payload) {

    if (payload.size() < kSeekHeaderSize + kSeekTrailerSize) {
        throw std::runtime_error("truncated AUR2 seek-index");
    }
    if (!std::equal(kSeekMagic.begin(), kSeekMagic.end(), payload.begin())) {
        throw std::runtime_error("invalid AUR2 seek-index magic");
    }
    if (read_u16(payload, 4) != kSeekIndexVersion) {
        throw std::runtime_error("unsupported AUR2 seek-index version");
    }
    if (read_u16(payload, 6) != kSeekIndexRecordSize) {
        throw std::runtime_error("unsupported AUR2 seek-index record size");
    }

    const auto count = read_u64(payload, 8);
    if (count > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("AUR2 seek-index record count exceeds address space");
    }
    const auto count_size = static_cast<std::size_t>(count);
    if (count_size >
        (std::numeric_limits<std::size_t>::max() - kSeekHeaderSize - kSeekTrailerSize)
        / kSeekIndexRecordSize) {
        throw std::runtime_error("AUR2 seek-index size overflow");
    }
    const auto expected_size =
        kSeekHeaderSize + count_size * kSeekIndexRecordSize + kSeekTrailerSize;
    if (payload.size() != expected_size) {
        throw std::runtime_error("AUR2 seek-index length mismatch");
    }

    const auto stored_crc = read_u32(payload, payload.size() - kSeekTrailerSize);
    const auto actual_crc = crc32(payload.first(payload.size() - kSeekTrailerSize));
    if (stored_crc != actual_crc) {
        throw std::runtime_error("AUR2 seek-index CRC32 mismatch");
    }

    std::vector<SeekIndexRecord> records;
    records.reserve(count_size);
    std::size_t pos = kSeekHeaderSize;
    for (std::size_t i = 0; i < count_size; ++i) {
        SeekIndexRecord record;
        record.section_type = read_u32(payload, pos + 0);
        record.section_flags = read_u32(payload, pos + 4);
        record.section_offset = read_u64(payload, pos + 8);
        record.payload_offset = read_u64(payload, pos + 16);
        record.payload_size = read_u64(payload, pos + 24);
        pos += kSeekIndexRecordSize;

        if (record.section_type == static_cast<std::uint32_t>(SectionType::SeekIndex)) {
            throw std::runtime_error("AUR2 seek-index cannot index itself");
        }
        if (record.payload_offset != checked_add(record.section_offset, kSectionHeaderSize)) {
            throw std::runtime_error("AUR2 seek-index payload offset mismatch");
        }
        records.push_back(record);
    }
    return records;
}

ByteBuffer attach_seek_index(std::span<const std::uint8_t> archive) {
    auto container = decode_container(archive);
    validate_container_structure(container);

    container.sections.erase(
        std::remove_if(
            container.sections.begin(),
            container.sections.end(),
            [](const Section& section) {
                return section.type == static_cast<std::uint32_t>(SectionType::SeekIndex);
            }),
        container.sections.end());

    const auto record_count = container.sections.size();
    const auto seek_payload_size =
        kSeekHeaderSize
        + record_count * static_cast<std::size_t>(kSeekIndexRecordSize)
        + kSeekTrailerSize;

    std::vector<SeekIndexRecord> records;
    records.reserve(record_count);

    std::uint64_t cursor = checked_add(
        kFixedHeaderSize,
        checked_add(kSectionHeaderSize, static_cast<std::uint64_t>(seek_payload_size)));

    for (const auto& section : container.sections) {
        SeekIndexRecord record;
        record.section_type = section.type;
        record.section_flags = section.flags;
        record.section_offset = cursor;
        record.payload_offset = checked_add(cursor, kSectionHeaderSize);
        record.payload_size = section.payload.size();
        records.push_back(record);

        cursor = checked_add(
            record.payload_offset,
            static_cast<std::uint64_t>(section.payload.size()));
    }

    Section seek;
    seek.type = static_cast<std::uint32_t>(SectionType::SeekIndex);
    seek.flags = SectionFlagIgnorable;
    seek.payload = encode_seek_index(records);

    container.header.feature_flags |= feature_bit(Feature::SeekIndex);
    container.sections.insert(container.sections.begin(), std::move(seek));

    auto out = encode_container(container.header, container.sections);
    validate_seek_index(out);
    return out;
}

void validate_seek_index(std::span<const std::uint8_t> archive) {
    const auto container = decode_container(archive);
    validate_container_structure(container);

    const bool flag =
        (container.header.feature_flags & feature_bit(Feature::SeekIndex)) != 0;

    std::size_t seek_count = 0;
    const Section* seek = nullptr;
    for (const auto& section : container.sections) {
        if (section.type == static_cast<std::uint32_t>(SectionType::SeekIndex)) {
            ++seek_count;
            seek = &section;
        }
    }

    if (!flag && seek_count == 0) {
        return;
    }
    if (flag != (seek_count == 1)) {
        throw std::runtime_error("AUR2 SEEK_INDEX feature flag/section mismatch");
    }
    if (container.sections.empty() || &container.sections.front() != seek) {
        throw std::runtime_error("AUR2 SEEK_INDEX must be the first section");
    }
    if (container.header.toc_offset != container.header.header_size) {
        throw std::runtime_error("AUR2 SEEK_INDEX is not located at TOC offset");
    }

    const auto records = decode_seek_index(seek->payload);
    if (records.size() + 1 != container.sections.size()) {
        throw std::runtime_error("AUR2 seek-index does not cover every non-index section");
    }

    std::uint64_t cursor = checked_add(
        container.header.header_size,
        checked_add(kSectionHeaderSize, static_cast<std::uint64_t>(seek->payload.size())));

    for (std::size_t i = 0; i < records.size(); ++i) {
        const auto& record = records[i];
        const auto& section = container.sections[i + 1];
        if (record.section_type != section.type ||
            record.section_flags != section.flags ||
            record.section_offset != cursor ||
            record.payload_offset != checked_add(cursor, kSectionHeaderSize) ||
            record.payload_size != section.payload.size()) {
            throw std::runtime_error("AUR2 seek-index record does not match section layout");
        }
        cursor = checked_add(
            record.payload_offset,
            static_cast<std::uint64_t>(section.payload.size()));
    }

    if (cursor != archive.size()) {
        throw std::runtime_error("AUR2 seek-index does not cover complete archive layout");
    }
}

} // namespace kephir2::aur2
