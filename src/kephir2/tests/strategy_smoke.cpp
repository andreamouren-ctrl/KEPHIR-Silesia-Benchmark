#include "kephir2/strategy.hpp"

#include <cassert>
#include <optional>

int main() {
    using namespace kephir2;

    GlobalRouter router;

    ArchiveFeatures repo_like{};
    repo_like.logical_bytes = 800'000;
    repo_like.file_count = 250;
    repo_like.average_file_bytes = 3'200.0;
    repo_like.median_file_bytes = 1'900.0;
    repo_like.small_file_fraction = 1.0;

    LayoutProbe flat_probe{};
    flat_probe.sampled_bytes = 800'000;
    flat_probe.flat_archive_bytes = 112'000;
    flat_probe.smart_archive_bytes = 116'000;

    auto repo_plan = router.plan(repo_like, Profile::Auto, flat_probe);
    assert(repo_plan.layout == Layout::Flat);
    assert(repo_plan.require_integrity_verification);

    ArchiveFeatures silesia_like{};
    silesia_like.logical_bytes = 212'000'000;
    silesia_like.file_count = 12;
    silesia_like.average_file_bytes = 17'600'000.0;
    silesia_like.median_file_bytes = 10'000'000.0;
    silesia_like.small_file_fraction = 0.0;

    silesia_like.sampled_content_groups = 5;
    silesia_like.sampled_dominant_file_fraction = 1.0 / 3.0;
    silesia_like.sampled_dominant_byte_fraction = 1.0 / 3.0;

    LayoutProbe smart_probe{};
    smart_probe.sampled_bytes = 2u * 1024u * 1024u;
    smart_probe.flat_archive_bytes = 754'225;
    smart_probe.smart_archive_bytes = 753'646;

    auto silesia_plan = router.plan(silesia_like, Profile::Auto, smart_probe);
    assert(silesia_plan.layout == Layout::Smart);
    assert(!silesia_plan.request_extended_probe);

    // EXP-82 regression: representative diversity is a confidence signal,
    // never a SMART preference. A near-tie measured in favor of FLAT must
    // remain FLAT.
    ArchiveFeatures mixed_like{};
    mixed_like.logical_bytes = 8u * 1024u * 1024u;
    mixed_like.file_count = 8;
    mixed_like.sampled_content_groups = 6;
    mixed_like.sampled_dominant_file_fraction = 0.25;
    mixed_like.sampled_dominant_byte_fraction = 0.25;

    LayoutProbe mixed_probe{};
    mixed_probe.sampled_bytes = 2u * 1024u * 1024u;
    mixed_probe.flat_archive_bytes = 262'924;
    mixed_probe.smart_archive_bytes = 263'260;

    auto mixed_plan = router.plan(mixed_like, Profile::Auto, mixed_probe);
    assert(mixed_plan.layout == Layout::Flat);
    assert(!mixed_plan.request_extended_probe);

    ArchiveFeatures homogeneous_large{};
    homogeneous_large.logical_bytes = 200'000'000;
    homogeneous_large.file_count = 10;
    homogeneous_large.sampled_content_groups = 1;
    homogeneous_large.sampled_dominant_file_fraction = 1.0;
    homogeneous_large.sampled_dominant_byte_fraction = 1.0;

    LayoutProbe ambiguous_probe{};
    ambiguous_probe.sampled_bytes = 2u * 1024u * 1024u;
    ambiguous_probe.flat_archive_bytes = 700'000;
    ambiguous_probe.smart_archive_bytes = 700'100;

    auto ambiguous_plan = router.plan(homogeneous_large, Profile::Auto, ambiguous_probe);
    assert(ambiguous_plan.request_extended_probe);

    ArchiveFeatures mixed_like{};
    mixed_like.logical_bytes = 8u * 1024u * 1024u;
    mixed_like.file_count = 8;
    mixed_like.sampled_content_groups = 6;
    mixed_like.sampled_dominant_file_fraction = 0.375;
    mixed_like.sampled_dominant_byte_fraction = 0.375;

    LayoutProbe mixed_probe{};
    mixed_probe.sampled_bytes = 2u * 1024u * 1024u;
    mixed_probe.flat_archive_bytes = 262'924;
    mixed_probe.smart_archive_bytes = 263'260;

    auto mixed_plan = router.plan(mixed_like, Profile::Auto, mixed_probe);
    assert(mixed_plan.layout == Layout::Flat);
    assert(!mixed_plan.request_extended_probe);

    auto fast_plan = router.plan(silesia_like, Profile::Fast, std::nullopt);
    assert(fast_plan.preferred_grain_bytes == 512u * 1024u);
    assert(!fast_plan.allow_structural_transforms);

    auto max_plan = router.plan(silesia_like, Profile::Max, std::nullopt);
    assert(max_plan.preferred_grain_bytes == 128u * 1024u);
    assert(max_plan.allow_structural_transforms);

    return 0;
}
