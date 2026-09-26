#include "kephir2/strategy.hpp"

#include <algorithm>

namespace kephir2 {

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

    if (probe && probe->valid()) {
        out.layout = (probe->smart_archive_bytes < probe->flat_archive_bytes)
            ? Layout::Smart
            : Layout::Flat;
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
