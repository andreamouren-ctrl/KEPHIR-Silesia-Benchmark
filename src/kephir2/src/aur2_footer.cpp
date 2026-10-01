#include "kephir2/aur2_footer.hpp"

#include "kephir2/aur2_seek.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>

namespace kephir2::aur2 {
namespace {

constexpr std::array<std::uint8_t, 4> kFooterMagic{'A', '2', 'F', '1'};

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
        throw std::runtime_error("truncated AUR2 footer uint16");
    }
    return static_cast<std::uint16_t>(data[offset]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[offset + 1]) << 8u);
}

std::uint32_t read_u32(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) {
        throw std::runtime_error("truncated AUR2 footer uint32");
    }
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

std::uint64_t read_u64(std::span<const std::uint8_t> data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 8) {
        throw std::runtime_error("truncated AUR2 footer uint64");
    }
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(data[offset + i]) << (8u * i);
    }
    return value;
}

const Section* find_footer(const Container& container, std::size_t& count) {
    count = 0;
    const Section* found = nullptr;
    for (const auto& section : container.sections) {
        if (section.type == kFooterSectionType) {
            ++count;
            found = &section;
        }
    }
    return found;
}

} // namespace

ByteBuffer encode_footer_payload(const FooterInfo& footer) {
    ByteBuffer out;
    out.reserve(kFooterPayloadSize);
    out.insert(out.end(), kFooterMagic.begin(), kFooterMagic.end());
    append_u16(out, kFooterVersion);
    append_u16(out, kFooterPayloadSize);
    append_u64(out, footer.body_size);
    append_u32(out, footer.body_crc32);
    append_u32(out, 0u);
    append_u32(out, crc32(out));
    append_u32(out, 0u);

    if (out.size() != kFooterPayloadSize) {
        throw std::runtime_error("internal AUR2 footer size mismatch");
    }
    return out;
}

FooterInfo decode_footer_payload(std::span<const std::uint8_t> payload) {
    if (payload.size() != kFooterPayloadSize) {
        throw std::runtime_error("AUR2 footer payload length mismatch");
    }
    if (!std::equal(kFooterMagic.begin(), kFooterMagic.end(), payload.begin())) {
        throw std::runtime_error("invalid AUR2 footer magic");
    }
    if (read_u16(payload, 4) != kFooterVersion) {
        throw std::runtime_error("unsupported AUR2 footer version");
    }
    if (read_u16(payload, 6) != kFooterPayloadSize) {
        throw std::runtime_error("unsupported AUR2 footer payload size");
    }
    if (read_u32(payload, 20) != 0 || read_u32(payload, 28) != 0) {
        throw std::runtime_error("AUR2 footer reserved field is non-zero");
    }

    const auto stored_payload_crc = read_u32(payload, 24);
    const auto actual_payload_crc = crc32(payload.first(24));
    if (stored_payload_crc != actual_payload_crc) {
        throw std::runtime_error("AUR2 footer payload CRC32 mismatch");
    }

    FooterInfo footer;
    footer.body_size = read_u64(payload, 8);
    footer.body_crc32 = read_u32(payload, 16);
    return footer;
}

ByteBuffer attach_footer_integrity(std::span<const std::uint8_t> archive) {
    auto container = decode_container(archive);
    validate_container_structure(container);

    container.sections.erase(
        std::remove_if(
            container.sections.begin(),
            container.sections.end(),
            [](const Section& section) {
                return section.type == kFooterSectionType;
            }),
        container.sections.end());

    // Rebuild the index after adding a fixed-size placeholder footer. Because
    // the final payload size is unchanged, replacing the placeholder does not
    // invalidate any SEEK_INDEX offsets.
    container.header.feature_flags |= kFeatureFooterIntegrity;

    Section footer;
    footer.type = kFooterSectionType;
    footer.flags = SectionFlagIgnorable;
    footer.payload = encode_footer_payload({0, 0});
    container.sections.push_back(std::move(footer));

    const auto preliminary = encode_container(container.header, container.sections);
    const auto indexed = attach_seek_index(preliminary);

    auto indexed_container = decode_container(indexed);
    validate_container_structure(indexed_container);
    if (indexed_container.sections.empty() ||
        indexed_container.sections.back().type != kFooterSectionType) {
        throw std::runtime_error("AUR2 footer is not the final section");
    }

    if (indexed.size() < kSectionHeaderSize + kFooterPayloadSize) {
        throw std::runtime_error("AUR2 footer archive is truncated");
    }
    const auto body_size = static_cast<std::uint64_t>(
        indexed.size() - kSectionHeaderSize - kFooterPayloadSize);
    const auto body_span = std::span<const std::uint8_t>(
        indexed.data(),
        static_cast<std::size_t>(body_size));
    const auto body_crc = crc32(body_span);

    indexed_container.sections.back().payload = encode_footer_payload({
        body_size,
        body_crc
    });

    const auto out = encode_container(
        indexed_container.header,
        indexed_container.sections);
    validate_footer_integrity(out);
    return out;
}

void validate_footer_integrity(std::span<const std::uint8_t> archive) {
    const auto container = decode_container(archive);
    validate_container_structure(container);

    const bool feature =
        (container.header.feature_flags & kFeatureFooterIntegrity) != 0;

    std::size_t count = 0;
    const auto* footer = find_footer(container, count);

    if (!feature && count == 0) {
        return;
    }
    if (!feature || count != 1 || footer == nullptr) {
        throw std::runtime_error("AUR2 footer feature flag/section mismatch");
    }
    if (container.sections.empty() || &container.sections.back() != footer) {
        throw std::runtime_error("AUR2 footer must be the final section");
    }
    if (footer->flags != SectionFlagIgnorable) {
        throw std::runtime_error("AUR2 footer must be ignorable for legacy readers");
    }

    const auto info = decode_footer_payload(footer->payload);
    const auto footer_total = static_cast<std::uint64_t>(
        kSectionHeaderSize + footer->payload.size());
    if (archive.size() < footer_total) {
        throw std::runtime_error("truncated AUR2 footer section");
    }
    const auto expected_body_size =
        static_cast<std::uint64_t>(archive.size()) - footer_total;
    if (info.body_size != expected_body_size) {
        throw std::runtime_error("AUR2 footer body size mismatch");
    }
    if (info.body_size > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("AUR2 footer body exceeds address space");
    }

    const auto actual_body_crc = crc32(
        archive.first(static_cast<std::size_t>(info.body_size)));
    if (actual_body_crc != info.body_crc32) {
        throw std::runtime_error("AUR2 footer body CRC32 mismatch");
    }

    // New footer-bearing archives are always indexed; this also verifies that
    // FTR1 is represented by the TOC and its fixed size/offset did not drift.
    validate_seek_index(archive);
}

} // namespace kephir2::aur2
