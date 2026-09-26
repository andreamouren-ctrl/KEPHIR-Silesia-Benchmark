#include "kephir2/strategy.hpp"

#include <algorithm>

namespace kephir2 {

namespace {
constexpr double kStage1StrongMargin = 0.02;
constexpr std::uint64_t kStage1ProbeBudget = 512u * 1024u;
constexpr std::uint64_t kStage2ProbeBudget = 2u * 1024u * 1024u;
constexpr std::uint64_t kSmallFullProbeLimit = 1u * 1024u * 1024u;
constexpr std::uint32_t kDiversityMinGroups = 3;
constexpr double kDiversityMaxDominantFileFraction = 0.75;
constexpr double kDiversityMaxDominantByteFraction = 0.80;
constexpr std::uint64_t kDiversityMinLogicalBytes = 8u * 1024u * 1024u;

// EXP-88 cheap gate. These values are inherited unchanged from EXP-86;
// holdout validation showed they are safe only as a FLAT fast-path gate.
constexpr double kGroupabilityMinAverageFileBytes = 512.0 * 1024.0;
constexpr double kGroupabilityMinRepeatableByteFraction = 0.60;
constexpr double kGroupabilityMaxDominantByteFraction = 0.75;

bool groupability_smart_candidate(const ArchiveFeatures& features) noexcept {
    return features.average_file_bytes >= kGroupabilityMinAverageFileBytes
        && features.repeatable_content_byte_fraction >= kGroupabilityMinRepeatableByteFraction
        && features.sampled_dominant_byte_fraction <= kGroupabilityMaxDominantByteFraction;
}

bool sample_is_representative(const ArchiveFeatures& features) noexcept {
    return features.logical_bytes >= kDiversityMinLogicalBytes
        && features.sampled_content_groups >= kDiversityMinGroups
        && features.sampled_dominant_file_fraction <= kDiversityMaxDominantFileFraction
        && features.sampled_dominant_byte_fraction <= kDiversityMaxDominantByteFraction;
}
} // namespace

Layout GlobalRouter::fallback_layout(const ArchiveFeatures& features) noexcept {
    // Conservative bootstrap rule used only when no bounded probe exists.
    // KEPHIR 2 is intentionally probe-first; metadata is a fallback, not the
    // primary decision engine.
    if (features.file_count == 0) {
        return Layout::Flat;
    }

    // Many tiny files are frequently dominated by manifest/group overhead.
    if (features.file_count >= 128 && features.small_file_fraction >= 0.80) {
        return Layout::Flat;
    }

    // Heterogeneous multi-file archives are the primary SMART use case.
    if (features.file_count >= 4) {
        return Layout::Smart;
    }

    return Layout::Flat;
}

StrategyPlan GlobalRouter::plan(
    const ArchiveFeatures& features,
    Profile requested_profile,
    const std::optional<LayoutProbe>& probe) const noexcept {

    StrategyPlan out{};
    out.profile = requested_profile;

    // EXP-84 deterministic-dominance / adaptive-budget AUTO router.
    // A single content family collapses SMART to one payload stream, so FLAT
    // dominates without any compression probe.
    if (features.file_count == 0) {
        out.layout = Layout::Flat;
    } else if (features.sampled_content_groups == 1) {
        out.layout = Layout::Flat;
    } else if (probe && probe->valid()) {
        const auto measured_layout = (probe->smart_archive_bytes < probe->flat_archive_bytes)
            ? Layout::Smart
            : Layout::Flat;
        const bool full_input_probe = features.logical_bytes != 0
            && probe->sampled_bytes >= features.logical_bytes;
        const double margin = probe->relative_margin();

        if (full_input_probe || margin >= kStage1StrongMargin) {
            out.layout = measured_layout;
        } else if (sample_is_representative(features)) {
            // Diversity establishes confidence only. It never chooses SMART
            // or FLAT; preserve the measured direction.
            out.layout = measured_layout;
        } else {
            const auto target = static_cast<std::size_t>(
                std::min<std::uint64_t>(kStage2ProbeBudget, features.logical_bytes));
            if (probe->sampled_bytes < target) {
                out.layout = measured_layout;
                out.requested_probe_bytes = target;
                out.request_extended_probe = true;
            } else {
                out.layout = measured_layout;
            }
        }
    } else {
        // EXP-88 hybrid gate:
        // a negative cheap groupability signal is allowed to finalize FLAT;
        // a positive SMART candidate is never trusted directly and must still
        // pass the measured EXP-84 bounded probe.
        if (requested_profile == Profile::Auto
            && !groupability_smart_candidate(features)) {
            out.layout = Layout::Flat;
        } else {
            out.layout = fallback_layout(features);
            const auto target = static_cast<std::size_t>(
                features.logical_bytes <= kSmallFullProbeLimit
                    ? features.logical_bytes
                    : std::min<std::uint64_t>(kStage1ProbeBudget, features.logical_bytes));
            if (target != 0) {
                out.requested_probe_bytes = target;
                out.request_initial_probe = true;
            }
        }
    }

    switch (requested_profile) {
    case Profile::Fast:
        out.preferred_grain_bytes = 512u * 1024u;
        out.allow_structural_transforms = false;
        out.allow_local_experience = true;
        break;

    case Profile::Max:
        out.preferred_grain_bytes = 128u * 1024u;
        out.allow_structural_transforms = true;
        out.allow_local_experience = true;
        break;

    case Profile::Balanced:
        out.preferred_grain_bytes = 256u * 1024u;
        out.allow_structural_transforms = true;
        out.allow_local_experience = true;
        break;

    case Profile::Auto:
    default:
        out.preferred_grain_bytes = 512u * 1024u;
        out.allow_structural_transforms = true;
        out.allow_local_experience = true;
        break;
    }

    // Integrity remains mandatory for every commercial profile.
    out.require_integrity_verification = true;
    return out;
}

} // namespace kephir2
