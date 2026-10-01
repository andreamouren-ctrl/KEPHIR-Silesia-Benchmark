#pragma once

#include "kephir2/aur2.hpp"

#include <cstdint>
#include <span>

namespace kephir2::aur2 {

inline constexpr std::uint64_t kFeatureFooterIntegrity =
    feature_bit(Feature::FooterIntegrity);
inline constexpr std::uint32_t kFooterSectionType =
    static_cast<std::uint32_t>(SectionType::FooterIntegrity);
inline constexpr std::uint16_t kFooterVersion = 1;
inline constexpr std::uint16_t kFooterPayloadSize = 32;

struct FooterInfo {
    std::uint64_t body_size{0};
    std::uint32_t body_crc32{0};

    bool operator==(const FooterInfo&) const = default;
};

[[nodiscard]] ByteBuffer encode_footer_payload(const FooterInfo& footer);
[[nodiscard]] FooterInfo decode_footer_payload(std::span<const std::uint8_t> payload);

// Adds or refreshes a fixed-size FTR1 section at the end of the container.
// The section is ignorable for older decoders. SEEK_INDEX is rebuilt so the
// footer itself is represented in the TOC without creating a circular checksum.
[[nodiscard]] ByteBuffer attach_footer_integrity(
    std::span<const std::uint8_t> archive);

// Legacy AUR2 archives without the footer remain valid. If either the feature
// flag or FTR1 section is present, both must be present and the body checksum,
// footer self-checksum, ordering and SEEK_INDEX layout are validated strictly.
void validate_footer_integrity(std::span<const std::uint8_t> archive);

} // namespace kephir2::aur2
