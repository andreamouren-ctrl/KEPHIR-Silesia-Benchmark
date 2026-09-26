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
};

struct LayoutProbe {
    std::uint64_t sampled_bytes{0};
    std::uint64_t flat_archive_bytes{0};
    std::uint64_t smart_archive_bytes{0};
    double elapsed_seconds{0.0};

    [[nodiscard]] bool valid() const noexcept {
        return sampled_bytes != 0 && flat_archive_bytes != 0 && smart_archive_bytes != 0;
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
