#include "kephir2/strategy.hpp"

#include <algorithm>

namespace kephir2 {

namespace {
constexpr double kStage1StrongMargin = 0.02;
constexpr std::uint32_t kDiversityMinGroups = 3;
constexpr double kDiversityMaxDominantFileFraction = 0.75;
constexpr double kDiversityMaxDominantByteFraction = 0.80;
constexpr std::uint64_t kDiversityMinLogicalBytes = 8u * 1024u * 1024u;
constexpr std::uint64_t kStage2ProbeBudget = 12u * 1024u * 1024u;

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

    // Deterministic dominance fast path:
    // when every file belongs to one content family, SMART would create one
    // payload group containing the same ordered concatenation as FLAT while
    // carrying additional grouping metadata. FLAT therefore dominates and no
    // compression probe is required.
    if (features.file_count > 0 && features.sampled_content_groups == 1) {
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
            // EXP-82: diversity is a confidence signal, not a SMART vote.
            // Preserve the measured direction, whether SMART or FLAT.
            out.layout = measured_layout;
        } else if (probe->sampled_bytes < kStage2ProbeBudget
                   && probe->sampled_bytes < features.logical_bytes) {
            // Homogeneous / weak evidence: request the larger bounded probe.
            out.layout = measured_layout;
            out.request_extended_probe = true;
        } else {
            // Maximum bounded evidence reached: preserve what was measured.
            out.layout = measured_layout;
        }
    } else {
        out.layout = fallback_layout(features);
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
