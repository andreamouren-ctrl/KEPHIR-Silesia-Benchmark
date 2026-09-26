#include "kephir2/planner.hpp"

namespace kephir2 {

PlanningResult CompressionPlanner::plan_directory(
    const std::filesystem::path& root,
    Profile profile,
    const std::optional<LayoutProbe>& probe,
    const AnalyzerOptions& analyzer_options) const {

    PlanningResult result{};
    result.features = analyzer_.analyze_directory(root, analyzer_options);
    result.strategy = router_.plan(result.features, profile, probe);
    return result;
}

} // namespace kephir2
