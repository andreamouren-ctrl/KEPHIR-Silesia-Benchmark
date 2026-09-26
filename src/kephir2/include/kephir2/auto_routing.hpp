#pragma once

#include "kephir2/backend.hpp"
#include "kephir2/planner.hpp"

#include <filesystem>
#include <vector>

namespace kephir2 {

struct ResolvedDirectoryStrategy {
    ArchiveFeatures features{};
    StrategyPlan strategy{};
    std::vector<LayoutProbe> probes{};
};

class ProductionAutoResolver {
public:
    [[nodiscard]] ResolvedDirectoryStrategy resolve(
        const std::filesystem::path& root,
        CompressionBackend& backend,
        Profile profile = Profile::Auto,
        const BackendOptions& backend_options = {},
        const AnalyzerOptions& analyzer_options = {}) const;
};

} // namespace kephir2
