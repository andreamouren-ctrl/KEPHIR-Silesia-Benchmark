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

    LayoutProbe smart_probe{};
    smart_probe.sampled_bytes = 12u * 1024u * 1024u;
    smart_probe.flat_archive_bytes = 3'850'000;
    smart_probe.smart_archive_bytes = 3'820'000;

    auto silesia_plan = router.plan(silesia_like, Profile::Auto, smart_probe);
    assert(silesia_plan.layout == Layout::Smart);

    auto fast_plan = router.plan(silesia_like, Profile::Fast, std::nullopt);
    assert(fast_plan.preferred_grain_bytes == 512u * 1024u);
    assert(!fast_plan.allow_structural_transforms);

    auto max_plan = router.plan(silesia_like, Profile::Max, std::nullopt);
    assert(max_plan.preferred_grain_bytes == 128u * 1024u);
    assert(max_plan.allow_structural_transforms);

    return 0;
}
