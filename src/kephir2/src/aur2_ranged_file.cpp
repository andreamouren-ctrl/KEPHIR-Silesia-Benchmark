#include "kephir2/aur2_ranged_file.hpp"

#include "kephir2/aur2_indexed_file.hpp"

#include <cstdint>
#include <fstream>
#include <limits>
#include <span>
#include <stdexcept>
#include <utility>

namespace kephir2::aur2 {
namespace {

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated ranged AUR2 uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated ranged AUR2 uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a) {
        throw std::runtime_error("ranged AUR2 offset overflow");
    }
    return a + b;
}

ByteBuffer read_exact(
    const std::filesystem::path& archive,
    std::uint64_t archive_size,
    std::uint64_t offset,
    std::uint64_t size) {

    if (offset > archive_size || size > archive_size - offset) {
        throw std::runtime_error("ranged AUR2 read exceeds archive");
    }
    if (size > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("ranged AUR2 read exceeds address space");
    }
    if (offset > static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) {
        throw std::runtime_error("ranged AUR2 offset exceeds stream range");
    }
    if (size > static_cast<std::uint64_t>(std::numeric_limits<std::streamsize>::max())) {
        throw std::runtime_error("ranged AUR2 size exceeds stream range");
    }

    ByteBuffer out(static_cast<std::size_t>(size));
    std::ifstream in(archive, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to open ranged AUR2 archive");
    }
    in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("unable to seek ranged AUR2 archive");
    }
    if (!out.empty()) {
        in.read(
            reinterpret_cast<char*>(out.data()),
            static_cast<std::streamsize>(out.size()));
        if (in.gcount() != static_cast<std::streamsize>(out.size())) {
            throw std::runtime_error("short read from ranged AUR2 archive");
        }
    }
    return out;
}

} // namespace

IndexedRangeReader::IndexedRangeReader(std::filesystem::path archive)
    : archive_(std::move(archive)) {

    validate_seek_index_file(archive_);

    archive_size_ = std::filesystem::file_size(archive_);
    const auto raw_header = read_exact(
        archive_, archive_size_, 0, kFixedHeaderSize);
    header_ = decode_header(raw_header);

    if ((header_.feature_flags & feature_bit(Feature::SeekIndex)) == 0) {
        throw std::runtime_error("ranged AUR2 reader requires SEEK_INDEX");
    }

    const auto seek_header = read_exact(
        archive_,
        archive_size_,
        header_.toc_offset,
        kSectionHeaderSize);
    if (read_u32(seek_header, 0)
        != static_cast<std::uint32_t>(SectionType::SeekIndex)) {
        throw std::runtime_error("ranged AUR2 TOC does not contain SEEK_INDEX");
    }

    const auto seek_payload_size = read_u64(seek_header, 8);
    const auto seek_payload_offset = checked_add(
        header_.toc_offset,
        kSectionHeaderSize);
    const auto seek_payload = read_exact(
        archive_,
        archive_size_,
        seek_payload_offset,
        seek_payload_size);
    records_ = decode_seek_index(seek_payload);

    const auto footer_raw = static_cast<std::uint32_t>(SectionType::FooterIntegrity);
    const SeekIndexRecord* footer = nullptr;
    for (const auto& record : records_) {
        if (record.section_type != footer_raw) continue;
        if (footer != nullptr) {
            throw std::runtime_error("duplicate ranged AUR2 footer record");
        }
        footer = &record;
    }

    const bool footer_feature =
        (header_.feature_flags & feature_bit(Feature::FooterIntegrity)) != 0;
    if (footer_feature) {
        if (!footer || header_.footer_offset != footer->section_offset) {
            throw std::runtime_error("ranged AUR2 footer offset/index mismatch");
        }
    } else if (header_.footer_offset != 0 || footer != nullptr) {
        throw std::runtime_error("ranged AUR2 unexpected footer offset/record");
    }
}

const SeekIndexRecord& IndexedRangeReader::require_section(SectionType type) const {
    const auto raw = static_cast<std::uint32_t>(type);
    const SeekIndexRecord* found = nullptr;
    for (const auto& record : records_) {
        if (record.section_type != raw) continue;
        if (found != nullptr) {
            throw std::runtime_error("duplicate ranged AUR2 section");
        }
        found = &record;
    }
    if (!found) {
        throw std::runtime_error("missing ranged AUR2 section");
    }
    return *found;
}

ByteBuffer IndexedRangeReader::read_section_payload(SectionType type) const {
    const auto& record = require_section(type);
    return read_exact(
        archive_,
        archive_size_,
        record.payload_offset,
        record.payload_size);
}

ByteBuffer IndexedRangeReader::read_section_range(
    SectionType type,
    std::uint64_t relative_offset,
    std::uint64_t size) const {

    const auto& record = require_section(type);
    if (relative_offset > record.payload_size ||
        size > record.payload_size - relative_offset) {
        throw std::out_of_range("ranged AUR2 section read exceeds payload");
    }

    return read_exact(
        archive_,
        archive_size_,
        checked_add(record.payload_offset, relative_offset),
        size);
}

} // namespace kephir2::aur2
