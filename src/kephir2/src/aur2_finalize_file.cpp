#include "kephir2/aur2_finalize_file.hpp"

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_footer.hpp"
#include "kephir2/aur2_metadata.hpp"
#include "kephir2/aur2_seek.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kephir2::aur2 {
namespace {

constexpr std::uint64_t kCopyChunkBytes = 1024ull * 1024ull;
constexpr std::size_t kSeekHeaderBytes = 16;
constexpr std::size_t kSeekTrailerBytes = 4;

struct SourceSection {
    std::uint32_t type{0};
    std::uint32_t flags{0};
    std::uint64_t payload_offset{0};
    std::uint64_t payload_size{0};
    ByteBuffer replacement;

    [[nodiscard]] bool has_replacement() const noexcept {
        return !replacement.empty() || type == static_cast<std::uint32_t>(SectionType::FileTable);
    }

    [[nodiscard]] std::uint64_t final_payload_size() const noexcept {
        return has_replacement()
            ? static_cast<std::uint64_t>(replacement.size())
            : payload_size;
    }
};

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated AUR2 finalizer uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated AUR2 finalizer uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a) {
        throw std::runtime_error("AUR2 finalizer offset overflow");
    }
    return a + b;
}

ByteBuffer read_exact(
    const std::filesystem::path& path,
    std::uint64_t offset,
    std::uint64_t size,
    std::uint64_t file_size) {

    if (offset > file_size || size > file_size - offset) {
        throw std::runtime_error("AUR2 finalizer read range exceeds source archive");
    }
    if (size > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("AUR2 finalizer read range exceeds address space");
    }
    if (offset > static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) {
        throw std::runtime_error("AUR2 finalizer offset exceeds stream range");
    }

    ByteBuffer out(static_cast<std::size_t>(size));
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to open AUR2 finalizer source archive");
    }
    in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("unable to seek AUR2 finalizer source archive");
    }
    if (!out.empty()) {
        in.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(out.size()));
        if (in.gcount() != static_cast<std::streamsize>(out.size())) {
            throw std::runtime_error("short read from AUR2 finalizer source archive");
        }
    }
    return out;
}

ByteBuffer encode_section_header(
    std::uint32_t type,
    std::uint32_t flags,
    std::uint64_t payload_size) {

    ByteBuffer out;
    out.reserve(kSectionHeaderSize);
    for (unsigned shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<std::uint8_t>((type >> shift) & 0xffu));
    }
    for (unsigned shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<std::uint8_t>((flags >> shift) & 0xffu));
    }
    for (unsigned shift = 0; shift < 64; shift += 8) {
        out.push_back(static_cast<std::uint8_t>((payload_size >> shift) & 0xffu));
    }
    return out;
}

void validate_section_header(std::uint32_t type, std::uint32_t flags) {
    const auto known_flags = static_cast<std::uint32_t>(
        SectionFlagIgnorable | SectionFlagRequired);
    if ((flags & ~known_flags) != 0) {
        throw std::runtime_error("AUR2 finalizer source section has unknown flags");
    }
    if ((flags & SectionFlagIgnorable) != 0 &&
        (flags & SectionFlagRequired) != 0) {
        throw std::runtime_error("AUR2 finalizer source section has conflicting flags");
    }
    if (!is_known_section_type(type) && (flags & SectionFlagIgnorable) == 0) {
        throw std::runtime_error("AUR2 finalizer source has unsupported required section");
    }
}

class Crc32Accumulator {
public:
    void update(std::span<const std::uint8_t> data) noexcept {
        for (const auto byte : data) {
            state_ ^= byte;
            for (unsigned bit = 0; bit < 8; ++bit) {
                const std::uint32_t mask = 0u - (state_ & 1u);
                state_ = (state_ >> 1u) ^ (0xedb88320u & mask);
            }
        }
    }

    [[nodiscard]] std::uint32_t value() const noexcept {
        return ~state_;
    }

private:
    std::uint32_t state_{0xffffffffu};
};

void write_bytes(
    std::ofstream& out,
    std::span<const std::uint8_t> bytes,
    Crc32Accumulator* crc) {

    if (!bytes.empty()) {
        out.write(
            reinterpret_cast<const char*>(bytes.data()),
            static_cast<std::streamsize>(bytes.size()));
        if (!out) {
            throw std::runtime_error("unable to write finalized AUR2 archive");
        }
        if (crc) crc->update(bytes);
    }
}

void copy_range(
    const std::filesystem::path& source,
    std::uint64_t offset,
    std::uint64_t size,
    std::ofstream& out,
    Crc32Accumulator& crc) {

    if (offset > static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) {
        throw std::runtime_error("AUR2 finalizer copy offset exceeds stream range");
    }

    std::ifstream in(source, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to reopen AUR2 finalizer source archive");
    }
    in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("unable to seek AUR2 finalizer source payload");
    }

    std::vector<std::uint8_t> buffer(static_cast<std::size_t>(kCopyChunkBytes));
    std::uint64_t remaining = size;
    while (remaining != 0) {
        const auto want = static_cast<std::size_t>(
            (std::min)(remaining, kCopyChunkBytes));
        in.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(want));
        if (in.gcount() != static_cast<std::streamsize>(want)) {
            throw std::runtime_error("short read while finalizing AUR2 payload");
        }
        const auto chunk = std::span<const std::uint8_t>(buffer.data(), want);
        write_bytes(out, chunk, &crc);
        remaining -= want;
    }
}

std::vector<SourceSection> scan_source_sections(
    const std::filesystem::path& base_archive,
    Header& header,
    const std::filesystem::path& source) {

    const auto archive_size = std::filesystem::file_size(base_archive);
    if (archive_size < kFixedHeaderSize) {
        throw std::runtime_error("truncated AUR2 finalizer source header");
    }
    header = decode_header(read_exact(base_archive, 0, kFixedHeaderSize, archive_size));

    std::vector<SourceSection> sections;
    std::uint64_t cursor = header.header_size;
    bool saw_file_table = false;

    while (cursor < archive_size) {
        if (archive_size - cursor < kSectionHeaderSize) {
            throw std::runtime_error("truncated AUR2 finalizer source section header");
        }
        const auto raw = read_exact(base_archive, cursor, kSectionHeaderSize, archive_size);
        const auto type = read_u32(raw, 0);
        const auto flags = read_u32(raw, 4);
        const auto payload_size = read_u64(raw, 8);
        validate_section_header(type, flags);

        const auto payload_offset = checked_add(cursor, kSectionHeaderSize);
        const auto next = checked_add(payload_offset, payload_size);
        if (next > archive_size) {
            throw std::runtime_error("truncated AUR2 finalizer source section payload");
        }

        if (type != static_cast<std::uint32_t>(SectionType::SeekIndex)
            && type != kFooterSectionType) {
            SourceSection section;
            section.type = type;
            section.flags = flags;
            section.payload_offset = payload_offset;
            section.payload_size = payload_size;

            if (type == static_cast<std::uint32_t>(SectionType::FileTable)) {
                if (saw_file_table) {
                    throw std::runtime_error("duplicate AUR2 FILE_TABLE in finalizer source");
                }
                saw_file_table = true;
                auto entries = decode_file_table(
                    read_exact(base_archive, payload_offset, payload_size, archive_size));
                capture_filesystem_metadata_entries(entries, source);
                section.replacement = encode_file_table(entries);
            }
            sections.push_back(std::move(section));
        }
        cursor = next;
    }

    if (!saw_file_table) {
        throw std::runtime_error("missing AUR2 FILE_TABLE in finalizer source");
    }
    if (sections.empty()) {
        throw std::runtime_error("AUR2 finalizer source has no payload sections");
    }
    return sections;
}

} // namespace

void finalize_archive_file_backed(
    const std::filesystem::path& base_archive,
    const std::filesystem::path& source,
    const std::filesystem::path& output_archive) {

    if (base_archive == output_archive) {
        throw std::invalid_argument("AUR2 finalizer input and output must differ");
    }

    Header header;
    auto sections = scan_source_sections(base_archive, header, source);

    const auto record_count = sections.size() + 1u; // + FTR1
    if (record_count >
        (std::numeric_limits<std::size_t>::max() - kSeekHeaderBytes - kSeekTrailerBytes)
        / kSeekIndexRecordSize) {
        throw std::runtime_error("AUR2 finalizer seek-index record count overflow");
    }

    const auto seek_payload_size = static_cast<std::uint64_t>(
        kSeekHeaderBytes
        + record_count * static_cast<std::size_t>(kSeekIndexRecordSize)
        + kSeekTrailerBytes);

    std::vector<SeekIndexRecord> records;
    records.reserve(record_count);

    std::uint64_t cursor = checked_add(
        kFixedHeaderSize,
        checked_add(kSectionHeaderSize, seek_payload_size));

    for (const auto& section : sections) {
        SeekIndexRecord record;
        record.section_type = section.type;
        record.section_flags = section.flags;
        record.section_offset = cursor;
        record.payload_offset = checked_add(cursor, kSectionHeaderSize);
        record.payload_size = section.final_payload_size();
        records.push_back(record);
        cursor = checked_add(record.payload_offset, record.payload_size);
    }

    const auto footer_offset = cursor;
    SeekIndexRecord footer_record;
    footer_record.section_type = kFooterSectionType;
    footer_record.section_flags = SectionFlagIgnorable;
    footer_record.section_offset = footer_offset;
    footer_record.payload_offset = checked_add(footer_offset, kSectionHeaderSize);
    footer_record.payload_size = kFooterPayloadSize;
    records.push_back(footer_record);

    const auto seek_payload = encode_seek_index(records);
    if (seek_payload.size() != seek_payload_size) {
        throw std::runtime_error("AUR2 finalizer seek-index size drift");
    }

    header.feature_flags &= ~(
        feature_bit(Feature::SeekIndex) |
        feature_bit(Feature::FooterIntegrity));
    header.feature_flags |=
        feature_bit(Feature::SeekIndex) |
        feature_bit(Feature::FooterIntegrity);
    header.toc_offset = kFixedHeaderSize;
    header.footer_offset = footer_offset;
    header.header_crc32 = 0;
    header.reserved = 0;

    const auto encoded_header = encode_header(header);
    const auto seek_header = encode_section_header(
        static_cast<std::uint32_t>(SectionType::SeekIndex),
        SectionFlagIgnorable,
        seek_payload.size());

    const auto parent = output_archive.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }
    std::ofstream out(output_archive, std::ios::binary | std::ios::trunc);
    if (!out) {
        throw std::runtime_error("unable to create finalized AUR2 archive");
    }

    Crc32Accumulator body_crc;
    write_bytes(out, encoded_header, &body_crc);
    write_bytes(out, seek_header, &body_crc);
    write_bytes(out, seek_payload, &body_crc);

    for (const auto& section : sections) {
        const auto payload_size = section.final_payload_size();
        const auto section_header = encode_section_header(
            section.type,
            section.flags,
            payload_size);
        write_bytes(out, section_header, &body_crc);

        if (section.has_replacement()) {
            write_bytes(out, section.replacement, &body_crc);
        } else {
            copy_range(
                base_archive,
                section.payload_offset,
                section.payload_size,
                out,
                body_crc);
        }
    }

    // FTR1's body checksum intentionally covers everything before the footer
    // section header. The footer payload has its own self-checksum.
    const auto body_size = footer_offset;
    const auto footer_payload = encode_footer_payload({body_size, body_crc.value()});
    const auto footer_header = encode_section_header(
        kFooterSectionType,
        SectionFlagIgnorable,
        footer_payload.size());
    write_bytes(out, footer_header, nullptr);
    write_bytes(out, footer_payload, nullptr);
    out.flush();
    if (!out) {
        throw std::runtime_error("unable to flush finalized AUR2 archive");
    }

    const auto expected_size = checked_add(
        footer_record.payload_offset,
        footer_record.payload_size);
    if (std::filesystem::file_size(output_archive) != expected_size) {
        throw std::runtime_error("AUR2 finalized archive size mismatch");
    }
}

} // namespace kephir2::aur2
