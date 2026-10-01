#include "kephir2/aur2.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#include <unordered_set>

namespace kephir2::aur2 {
namespace {

constexpr std::array<std::uint8_t, 8> kMagic{
    'A', 'U', 'R', '2', 0x0d, 0x0a, 0x1a, 0x0a
};

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

void write_u16(ByteBuffer& out, std::size_t offset, std::uint16_t value) {
    out.at(offset + 0) = static_cast<std::uint8_t>(value & 0xffu);
    out.at(offset + 1) = static_cast<std::uint8_t>((value >> 8u) & 0xffu);
}

void write_u32(ByteBuffer& out, std::size_t offset, std::uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) {
        out.at(offset + i) = static_cast<std::uint8_t>((value >> (8u * i)) & 0xffu);
    }
}

void write_u64(ByteBuffer& out, std::size_t offset, std::uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) {
        out.at(offset + i) = static_cast<std::uint8_t>((value >> (8u * i)) & 0xffu);
    }
}

std::uint16_t read_u16(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 2) {
        throw std::runtime_error("truncated AUR2 uint16");
    }
    return static_cast<std::uint16_t>(data[offset]) |
           static_cast<std::uint16_t>(static_cast<std::uint16_t>(data[offset + 1]) << 8u);
}

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated AUR2 uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated AUR2 uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t zigzag_encode(std::int64_t value) noexcept {
    const auto sign = value < 0 ? std::numeric_limits<std::uint64_t>::max() : 0ull;
    return (static_cast<std::uint64_t>(value) << 1u) ^ sign;
}

std::int64_t zigzag_decode(std::uint64_t value) noexcept {
    const auto magnitude = static_cast<std::int64_t>(value >> 1u);
    return (value & 1u) == 0 ? magnitude : -magnitude - 1;
}

void validate_section_flags(std::uint32_t flags) {
    const auto known = static_cast<std::uint32_t>(SectionFlagIgnorable | SectionFlagRequired);
    if ((flags & ~known) != 0) {
        throw std::runtime_error("AUR2 section has unknown flags");
    }
    if ((flags & SectionFlagIgnorable) != 0 && (flags & SectionFlagRequired) != 0) {
        throw std::runtime_error("AUR2 section cannot be both required and ignorable");
    }
}

void validate_section(const Section& section) {
    validate_section_flags(section.flags);
    if (!is_known_section_type(section.type) &&
        (section.flags & SectionFlagIgnorable) == 0) {
        throw std::runtime_error("unsupported required AUR2 section");
    }
}

} // namespace

std::uint32_t crc32(std::span<const std::uint8_t> data) noexcept {
    std::uint32_t crc = 0xffffffffu;
    for (const auto byte : data) {
        crc ^= byte;
        for (unsigned bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1u) ^ (0xedb88320u & mask);
        }
    }
    return ~crc;
}

bool is_known_section_type(std::uint32_t type) noexcept {
    switch (static_cast<SectionType>(type)) {
        case SectionType::FileTable:
        case SectionType::CodecDescriptor:
        case SectionType::BlockTable:
        case SectionType::Data:
        case SectionType::Integrity:
        case SectionType::Encryption:
        case SectionType::Recovery:
        case SectionType::SeekIndex:
        case SectionType::ExtendedMetadata:
        case SectionType::UserMetadata:
        case SectionType::FooterIntegrity:
            return true;
    }
    return false;
}

bool is_safe_relative_path(std::string_view path) noexcept {
    if (path.empty() || path.front() == '/' || path.find('\\') != std::string_view::npos ||
        path.find('\0') != std::string_view::npos) {
        return false;
    }

    std::size_t begin = 0;
    bool first = true;
    while (begin <= path.size()) {
        const auto end = path.find('/', begin);
        const auto stop = end == std::string_view::npos ? path.size() : end;
        const auto part = path.substr(begin, stop - begin);

        if (part.empty() || part == "." || part == "..") {
            return false;
        }
        if (first && part.size() >= 2 && part[1] == ':') {
            return false;
        }

        first = false;
        if (end == std::string_view::npos) {
            break;
        }
        begin = end + 1;
    }
    return true;
}

ByteBuffer encode_header(const Header& header) {
    if (header.container_major != kContainerMajor) {
        throw std::runtime_error("AUR2 encoder only writes container major 2");
    }
    if (header.header_size != kFixedHeaderSize) {
        throw std::runtime_error("AUR2 v2.0 requires a 64-byte fixed header");
    }
    if (header.reserved != 0) {
        throw std::runtime_error("AUR2 reserved header field must be zero");
    }

    ByteBuffer out(kFixedHeaderSize, 0);
    std::copy(kMagic.begin(), kMagic.end(), out.begin());
    write_u16(out, 8, header.container_major);
    write_u16(out, 10, header.container_minor);
    write_u32(out, 12, header.header_size);
    write_u64(out, 16, header.feature_flags);
    write_u64(out, 24, header.archive_id);
    write_u64(out, 32, header.logical_size);
    write_u64(out, 40, header.toc_offset);
    write_u64(out, 48, header.footer_offset);
    write_u32(out, 60, 0);

    const auto checksum = crc32(std::span<const std::uint8_t>(out.data(), 56));
    write_u32(out, 56, checksum);
    return out;
}

Header decode_header(std::span<const std::uint8_t> data) {
    if (data.size() < kFixedHeaderSize) {
        throw std::runtime_error("truncated AUR2 fixed header");
    }
    if (!std::equal(kMagic.begin(), kMagic.end(), data.begin())) {
        throw std::runtime_error("not an AUR2 archive");
    }

    Header header;
    header.container_major = read_u16(data, 8);
    header.container_minor = read_u16(data, 10);
    header.header_size = read_u32(data, 12);
    header.feature_flags = read_u64(data, 16);
    header.archive_id = read_u64(data, 24);
    header.logical_size = read_u64(data, 32);
    header.toc_offset = read_u64(data, 40);
    header.footer_offset = read_u64(data, 48);
    header.header_crc32 = read_u32(data, 56);
    header.reserved = read_u32(data, 60);

    if (header.container_major != kContainerMajor) {
        throw std::runtime_error("unsupported AUR container major version");
    }
    if (header.header_size != kFixedHeaderSize) {
        throw std::runtime_error("unsupported AUR2 header size");
    }
    if (header.reserved != 0) {
        throw std::runtime_error("AUR2 reserved header field is non-zero");
    }

    const auto expected = crc32(data.first(56));
    if (header.header_crc32 != expected) {
        throw std::runtime_error("AUR2 header CRC32 mismatch");
    }
    return header;
}

ByteBuffer encode_codec_descriptor(const CodecDescriptor& descriptor) {
    if (descriptor.codec_id == 0) {
        throw std::runtime_error("AUR2 codec id cannot be zero");
    }
    if (descriptor.private_data.size() > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("AUR2 codec private data is too large");
    }

    ByteBuffer out;
    out.reserve(24 + descriptor.private_data.size());
    append_u32(out, descriptor.codec_id);
    append_u16(out, descriptor.codec_major);
    append_u16(out, descriptor.codec_minor);
    append_u16(out, descriptor.minimum_decoder_major);
    append_u16(out, descriptor.minimum_decoder_minor);
    append_u64(out, descriptor.codec_flags);
    append_u32(out, static_cast<std::uint32_t>(descriptor.private_data.size()));
    out.insert(out.end(), descriptor.private_data.begin(), descriptor.private_data.end());
    return out;
}

CodecDescriptor decode_codec_descriptor(std::span<const std::uint8_t> data) {
    if (data.size() < 24) {
        throw std::runtime_error("truncated AUR2 codec descriptor");
    }

    CodecDescriptor descriptor;
    descriptor.codec_id = read_u32(data, 0);
    descriptor.codec_major = read_u16(data, 4);
    descriptor.codec_minor = read_u16(data, 6);
    descriptor.minimum_decoder_major = read_u16(data, 8);
    descriptor.minimum_decoder_minor = read_u16(data, 10);
    descriptor.codec_flags = read_u64(data, 12);
    const auto private_size = read_u32(data, 20);

    if (descriptor.codec_id == 0) {
        throw std::runtime_error("AUR2 codec id cannot be zero");
    }
    if (private_size != data.size() - 24) {
        throw std::runtime_error("AUR2 codec descriptor length mismatch");
    }

    descriptor.private_data.assign(data.begin() + 24, data.end());
    return descriptor;
}

ByteBuffer encode_file_table(std::span<const FileEntry> entries) {
    ByteBuffer out;
    put_varint(out, entries.size());

    std::unordered_set<std::uint64_t> ids;
    std::unordered_set<std::string> paths;
    ids.reserve(entries.size());
    paths.reserve(entries.size());

    for (const auto& entry : entries) {
        if (!is_safe_relative_path(entry.path)) {
            throw std::runtime_error("unsafe AUR2 file-table path");
        }
        if (!ids.insert(entry.entry_id).second) {
            throw std::runtime_error("duplicate AUR2 entry id");
        }
        if (!paths.insert(entry.path).second) {
            throw std::runtime_error("duplicate AUR2 entry path");
        }
        if (entry.type != EntryType::File && entry.type != EntryType::Directory) {
            throw std::runtime_error("unknown AUR2 entry type");
        }
        if (entry.type == EntryType::Directory && entry.logical_size != 0) {
            throw std::runtime_error("AUR2 directory logical size must be zero");
        }

        put_varint(out, entry.entry_id);
        put_varint(out, static_cast<std::uint64_t>(entry.type));
        put_varint(out, entry.path.size());
        out.insert(
            out.end(),
            reinterpret_cast<const std::uint8_t*>(entry.path.data()),
            reinterpret_cast<const std::uint8_t*>(entry.path.data() + entry.path.size()));
        put_varint(out, entry.logical_size);
        put_varint(out, entry.stream_id);
        put_varint(out, entry.stream_offset);
        put_varint(out, entry.attributes);
        put_varint(out, zigzag_encode(entry.mtime_unix_ns));
    }
    return out;
}

std::vector<FileEntry> decode_file_table(std::span<const std::uint8_t> data) {
    std::size_t pos = 0;
    const auto count = get_varint(data, pos);
    if (count > data.size()) {
        throw std::runtime_error("AUR2 file-table entry count is not plausible");
    }

    std::vector<FileEntry> entries;
    entries.reserve(static_cast<std::size_t>(count));
    std::unordered_set<std::uint64_t> ids;
    std::unordered_set<std::string> paths;
    ids.reserve(static_cast<std::size_t>(count));
    paths.reserve(static_cast<std::size_t>(count));

    for (std::uint64_t i = 0; i < count; ++i) {
        FileEntry entry;
        entry.entry_id = get_varint(data, pos);
        const auto raw_type = get_varint(data, pos);
        if (raw_type > static_cast<std::uint64_t>(EntryType::Directory)) {
            throw std::runtime_error("unknown AUR2 entry type");
        }
        entry.type = static_cast<EntryType>(raw_type);

        const auto path_size = get_varint(data, pos);
        if (path_size > data.size() - pos) {
            throw std::runtime_error("truncated AUR2 file-table path");
        }
        entry.path.assign(
            reinterpret_cast<const char*>(data.data() + pos),
            static_cast<std::size_t>(path_size));
        pos += static_cast<std::size_t>(path_size);

        if (!is_safe_relative_path(entry.path)) {
            throw std::runtime_error("unsafe AUR2 file-table path");
        }

        entry.logical_size = get_varint(data, pos);
        entry.stream_id = get_varint(data, pos);
        entry.stream_offset = get_varint(data, pos);
        const auto attributes = get_varint(data, pos);
        if (attributes > std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error("AUR2 file attributes overflow");
        }
        entry.attributes = static_cast<std::uint32_t>(attributes);
        entry.mtime_unix_ns = zigzag_decode(get_varint(data, pos));

        if (entry.type == EntryType::Directory && entry.logical_size != 0) {
            throw std::runtime_error("AUR2 directory logical size must be zero");
        }
        if (!ids.insert(entry.entry_id).second) {
            throw std::runtime_error("duplicate AUR2 entry id");
        }
        if (!paths.insert(entry.path).second) {
            throw std::runtime_error("duplicate AUR2 entry path");
        }

        entries.push_back(std::move(entry));
    }

    if (pos != data.size()) {
        throw std::runtime_error("AUR2 file-table trailing bytes");
    }
    return entries;
}

ByteBuffer encode_container(
    const Header& input_header,
    std::span<const Section> sections) {

    Header header = input_header;
    header.container_major = kContainerMajor;
    header.header_size = kFixedHeaderSize;
    header.toc_offset = sections.empty() ? 0 : kFixedHeaderSize;
    header.footer_offset = 0;
    header.header_crc32 = 0;
    header.reserved = 0;

    std::uint64_t cursor = kFixedHeaderSize;
    std::size_t footer_count = 0;
    for (std::size_t i = 0; i < sections.size(); ++i) {
        const auto& section = sections[i];
        validate_section(section);

        if (section.type == static_cast<std::uint32_t>(SectionType::FooterIntegrity)) {
            ++footer_count;
            if (footer_count != 1 || i + 1 != sections.size()) {
                throw std::runtime_error("AUR2 footer must be unique and final");
            }
            header.footer_offset = cursor;
        }

        if (section.payload.size() >
            std::numeric_limits<std::uint64_t>::max() - cursor - kSectionHeaderSize) {
            throw std::runtime_error("AUR2 container size overflow");
        }
        cursor += kSectionHeaderSize + static_cast<std::uint64_t>(section.payload.size());
    }

    ByteBuffer out = encode_header(header);
    for (const auto& section : sections) {
        append_u32(out, section.type);
        append_u32(out, section.flags);
        append_u64(out, section.payload.size());
        out.insert(out.end(), section.payload.begin(), section.payload.end());
    }

    return out;
}

Container decode_container(std::span<const std::uint8_t> data) {
    Container container;
    container.header = decode_header(data);

    std::size_t pos = container.header.header_size;
    if (pos == data.size()) {
        if (container.header.toc_offset != 0) {
            throw std::runtime_error("AUR2 TOC offset points to missing sections");
        }
        if (container.header.footer_offset != 0) {
            throw std::runtime_error("AUR2 footer offset points to missing section");
        }
        return container;
    }

    if (container.header.toc_offset != container.header.header_size) {
        throw std::runtime_error("AUR2 v2.0 TOC offset mismatch");
    }
    if (container.header.footer_offset != 0 &&
        (container.header.footer_offset < container.header.header_size ||
         container.header.footer_offset >= data.size())) {
        throw std::runtime_error("AUR2 footer offset is outside section area");
    }

    std::size_t footer_count = 0;
    while (pos < data.size()) {
        if (data.size() - pos < kSectionHeaderSize) {
            throw std::runtime_error("truncated AUR2 section header");
        }

        const auto section_offset = static_cast<std::uint64_t>(pos);
        Section section;
        section.type = read_u32(data, pos + 0);
        section.flags = read_u32(data, pos + 4);
        const auto payload_size = read_u64(data, pos + 8);
        pos += kSectionHeaderSize;

        validate_section_flags(section.flags);
        if (payload_size > data.size() - pos) {
            throw std::runtime_error("truncated AUR2 section payload");
        }
        if (payload_size > std::numeric_limits<std::size_t>::max()) {
            throw std::runtime_error("AUR2 section payload is too large for this platform");
        }

        section.payload.assign(
            data.begin() + static_cast<std::ptrdiff_t>(pos),
            data.begin() + static_cast<std::ptrdiff_t>(pos + static_cast<std::size_t>(payload_size)));
        pos += static_cast<std::size_t>(payload_size);

        validate_section(section);
        if (section.type == static_cast<std::uint32_t>(SectionType::FooterIntegrity)) {
            ++footer_count;
            if (footer_count != 1) {
                throw std::runtime_error("duplicate AUR2 footer section");
            }
            if (container.header.footer_offset != section_offset) {
                throw std::runtime_error("AUR2 footer offset mismatch");
            }
            if (pos != data.size()) {
                throw std::runtime_error("AUR2 footer must be the final section");
            }
        }

        container.sections.push_back(std::move(section));
    }

    if (footer_count == 0 && container.header.footer_offset != 0) {
        throw std::runtime_error("AUR2 footer offset has no matching section");
    }
    if (footer_count == 1 && container.header.footer_offset == 0) {
        throw std::runtime_error("AUR2 footer section is missing header offset");
    }

    return container;
}

} // namespace kephir2::aur2
