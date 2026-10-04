#pragma once

#include "kephir2/archive.hpp"

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace kephir2::aur2 {

inline constexpr std::uint16_t kContainerMajor = 2;
inline constexpr std::uint16_t kContainerMinor = 0;
inline constexpr std::uint32_t kFixedHeaderSize = 64;
inline constexpr std::uint32_t kSectionHeaderSize = 16;

inline constexpr std::uint32_t make_fourcc(char a, char b, char c, char d) noexcept {
    return static_cast<std::uint32_t>(static_cast<unsigned char>(a)) |
           (static_cast<std::uint32_t>(static_cast<unsigned char>(b)) << 8u) |
           (static_cast<std::uint32_t>(static_cast<unsigned char>(c)) << 16u) |
           (static_cast<std::uint32_t>(static_cast<unsigned char>(d)) << 24u);
}

inline constexpr std::uint32_t kCodecKephir = make_fourcc('K', 'P', 'H', 'R');

enum class Feature : std::uint64_t {
    Directory         = 1ull << 0u,
    MultiStream       = 1ull << 1u,
    Integrity         = 1ull << 2u,
    SeekIndex         = 1ull << 3u,
    Encryption        = 1ull << 4u,
    Recovery          = 1ull << 5u,
    ExtendedMetadata = 1ull << 6u,
    Kephir2           = 1ull << 7u,
    LegacyPayload     = 1ull << 8u,
    FooterIntegrity   = 1ull << 9u,
};

[[nodiscard]] constexpr std::uint64_t feature_bit(Feature feature) noexcept {
    return static_cast<std::uint64_t>(feature);
}

enum class SectionType : std::uint32_t {
    FileTable         = 0x0001u,
    CodecDescriptor   = 0x0002u,
    BlockTable        = 0x0003u,
    Data              = 0x0004u,
    Integrity         = 0x0005u,
    Encryption        = 0x0006u,
    Recovery          = 0x0007u,
    SeekIndex         = 0x0008u,
    ExtendedMetadata = 0x0009u,
    UserMetadata      = 0x000au,
    FooterIntegrity   = make_fourcc('F', 'T', 'R', '1'),
};

enum SectionFlags : std::uint32_t {
    SectionFlagNone      = 0,
    SectionFlagIgnorable = 1u << 0u,
    SectionFlagRequired  = 1u << 1u,
};

enum class EntryType : std::uint8_t {
    File = 0,
    Directory = 1,
};

struct Header {
    std::uint16_t container_major{kContainerMajor};
    std::uint16_t container_minor{kContainerMinor};
    std::uint32_t header_size{kFixedHeaderSize};
    std::uint64_t feature_flags{0};
    std::uint64_t archive_id{0};
    std::uint64_t logical_size{0};
    std::uint64_t toc_offset{0};
    std::uint64_t footer_offset{0};
    std::uint32_t header_crc32{0};
    std::uint32_t reserved{0};

    bool operator==(const Header&) const = default;
};

struct Section {
    std::uint32_t type{0};
    std::uint32_t flags{SectionFlagNone};
    ByteBuffer payload;

    bool operator==(const Section&) const = default;
};

struct CodecDescriptor {
    std::uint32_t codec_id{kCodecKephir};
    std::uint16_t codec_major{2};
    std::uint16_t codec_minor{0};
    std::uint16_t minimum_decoder_major{2};
    std::uint16_t minimum_decoder_minor{0};
    std::uint64_t codec_flags{0};
    ByteBuffer private_data;

    bool operator==(const CodecDescriptor&) const = default;
};

struct StreamRecord {
    std::uint64_t stream_id{0};
    std::uint64_t payload_offset{0};
    std::uint64_t compressed_size{0};
    std::uint64_t raw_size{0};
    std::uint32_t codec_id{kCodecKephir};
    std::uint64_t codec_flags{0};

    bool operator==(const StreamRecord&) const = default;
};

struct IntegrityRecord {
    std::uint64_t stream_id{0};
    std::uint32_t payload_crc32{0};

    bool operator==(const IntegrityRecord&) const = default;
};

struct FileEntry {
    std::uint64_t entry_id{0};
    EntryType type{EntryType::File};
    std::string path;
    std::uint64_t logical_size{0};
    std::uint64_t stream_id{0};
    std::uint64_t stream_offset{0};
    std::uint32_t attributes{0};
    std::int64_t mtime_unix_ns{0};

    bool operator==(const FileEntry&) const = default;
};

struct Container {
    Header header;
    std::vector<Section> sections;

    bool operator==(const Container&) const = default;
};

[[nodiscard]] std::uint32_t crc32(std::span<const std::uint8_t> data) noexcept;

[[nodiscard]] ByteBuffer encode_header(const Header& header);
[[nodiscard]] Header decode_header(std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_codec_descriptor(const CodecDescriptor& descriptor);
[[nodiscard]] CodecDescriptor decode_codec_descriptor(std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_stream_table(std::span<const StreamRecord> streams);
[[nodiscard]] std::vector<StreamRecord> decode_stream_table(std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_integrity_table(std::span<const IntegrityRecord> records);
[[nodiscard]] std::vector<IntegrityRecord> decode_integrity_table(std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_file_table(std::span<const FileEntry> entries);
[[nodiscard]] std::vector<FileEntry> decode_file_table(std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_container(
    const Header& header,
    std::span<const Section> sections);

[[nodiscard]] Container decode_container(std::span<const std::uint8_t> data);

void validate_container_structure(const Container& container);

[[nodiscard]] bool is_known_section_type(std::uint32_t type) noexcept;
[[nodiscard]] bool is_safe_relative_path(std::string_view path) noexcept;

} // namespace kephir2::aur2
