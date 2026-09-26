#pragma once

#include "kephir2/analyzer.hpp"
#include "kephir2/strategy.hpp"

#include <filesystem>
#include <optional>

namespace kephir2 {

struct PlanningResult {
    ArchiveFeatures features{};
    StrategyPlan strategy{};
};

class CompressionPlanner {
public:
    [[nodiscard]] PlanningResult plan_directory(
        const std::filesystem::path& root,
        Profile profile = Profile::Auto,
        const std::optional<LayoutProbe>& probe = std::nullopt,
        const AnalyzerOptions& analyzer_options = {}) const;

private:
    ContentAnalyzer analyzer_{};
    GlobalRouter router_{};
};

} // namespace kephir2
