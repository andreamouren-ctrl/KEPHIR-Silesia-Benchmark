#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>

namespace kephir2 {

enum class Profile : std::uint8_t {
    Auto,
    Fast,
    Balanced,
    Max
};

enum class Layout : std::uint8_t {
    Flat,
    Smart,
    Hybrid
};

enum class Transform : std::uint8_t {
    Base,
    Delta2Transpose2,
    Delta4Transpose4,
    Delta16Transpose16,
    Delta1024Transpose1024,
    WordXor16Transpose2,
    TextToken
};

struct ArchiveFeatures {
    std::uint64_t logical_bytes{0};
    std::uint64_t file_count{0};
    double average_file_bytes{0.0};
    double median_file_bytes{0.0};
    double small_file_fraction{0.0};

    // Bounded analyzer signals. They describe sampled content only and are
    // intentionally independent of file extension/name.
    double sampled_entropy{0.0};
    double sampled_printable_fraction{0.0};
    double sampled_zero_fraction{0.0};

    // Content-first diversity from the bounded sample.
    std::uint32_t sampled_content_groups{0};
    std::uint32_t multi_file_content_groups{0};
    double sampled_dominant_file_fraction{1.0};
    double sampled_dominant_byte_fraction{1.0};
    double repeatable_content_byte_fraction{0.0};

    // Exact file-order boundary signal for the current 512 KiB production
    // parent segmentation. A mixed parent contains bytes from more than one
    // content class in FLAT order.
    std::uint64_t flat_parent_count{0};
    std::uint64_t flat_mixed_parent_count{0};
    double flat_mixed_parent_byte_fraction{0.0};
};

struct LayoutProbe {
    std::uint64_t sampled_bytes{0};
    std::uint64_t flat_archive_bytes{0};
    std::uint64_t smart_archive_bytes{0};
    double elapsed_seconds{0.0};

    [[nodiscard]] bool valid() const noexcept {
        return sampled_bytes != 0 && flat_archive_bytes != 0 && smart_archive_bytes != 0;
    }

    [[nodiscard]] double relative_margin() const noexcept {
        const auto best = flat_archive_bytes < smart_archive_bytes ? flat_archive_bytes : smart_archive_bytes;
        const auto worst = flat_archive_bytes < smart_archive_bytes ? smart_archive_bytes : flat_archive_bytes;
        return best == 0 ? 0.0 : static_cast<double>(worst - best) / static_cast<double>(best);
    }
};

struct StrategyPlan {
    Profile profile{Profile::Auto};
    Layout layout{Layout::Flat};
    std::size_t parent_chunk_bytes{512u * 1024u};
    std::size_t preferred_grain_bytes{512u * 1024u};
    bool allow_structural_transforms{true};
    bool allow_local_experience{true};
    bool require_integrity_verification{true};

    // AUTO routing contract. Zero means the layout decision is final.
    // A non-zero value asks the caller to measure SMART and FLAT on a
    // representative sample of at most this many payload bytes.
    std::size_t requested_probe_bytes{0};

    // Compatibility/status flags derived from requested_probe_bytes.
    bool request_initial_probe{false};
    bool request_extended_probe{false};
};

class GlobalRouter {
public:
    [[nodiscard]] StrategyPlan plan(
        const ArchiveFeatures& features,
        Profile requested_profile,
        const std::optional<LayoutProbe>& probe = std::nullopt) const noexcept;

private:
    [[nodiscard]] static Layout fallback_layout(const ArchiveFeatures& features) noexcept;
};

} // namespace kephir2
