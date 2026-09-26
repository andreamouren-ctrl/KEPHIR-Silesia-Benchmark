#include "kephir2/packing.hpp"

#include <algorithm>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>

namespace kephir2 {
namespace {

std::string relative_utf8(
    const std::filesystem::path& path,
    const std::filesystem::path& root) {

    const auto rel = path.lexically_relative(root).generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(rel.data()),
        rel.size());
}

} // namespace

DirectoryPackingPlan build_directory_packing_plan(
    const std::filesystem::path& root,
    const ContentAnalyzer& analyzer) {

    DirectoryPackingPlan plan;
    const auto paths = collect_directory_files(root);

    plan.files.reserve(paths.size());

    std::vector<std::string> group_names;
    group_names.reserve(paths.size());

    for (const auto& path : paths) {
        const auto analysis = analyzer.analyze_file(path);
        const auto group = std::string(to_string(analysis.content_class));
        const auto size = std::filesystem::file_size(path);

        plan.files.push_back({
            relative_utf8(path, root),
            analysis.content_class,
            group,
            0,
            size,
            0
        });
        group_names.push_back(group);
    }

    std::sort(group_names.begin(), group_names.end());
    group_names.erase(
        std::unique(group_names.begin(), group_names.end()),
        group_names.end());

    std::map<std::string, std::uint64_t> group_ids;
    plan.groups.reserve(group_names.size());

    for (std::size_t i = 0; i < group_names.size(); ++i) {
        group_ids.emplace(group_names[i], static_cast<std::uint64_t>(i));
        plan.groups.push_back({group_names[i], 0, {}});
    }

    std::vector<ManifestRecord> manifest_records;
    manifest_records.reserve(plan.files.size());

    for (std::size_t i = 0; i < plan.files.size(); ++i) {
        auto& file = plan.files[i];
        const auto it = group_ids.find(file.group_name);
        if (it == group_ids.end()) {
            throw std::runtime_error("packing group id lookup failed");
        }

        file.group_id = it->second;
        auto& group = plan.groups[static_cast<std::size_t>(file.group_id)];

        if (file.size > std::numeric_limits<std::uint64_t>::max() - group.raw_length) {
            throw std::runtime_error("packing group raw length overflow");
        }

        file.group_offset = group.raw_length;
        group.raw_length += file.size;
        group.file_indices.push_back(i);

        manifest_records.push_back({
            file.path,
            file.group_id,
            file.size
        });
    }

    plan.manifest = encode_manifest(manifest_records);
    return plan;
}

} // namespace kephir2
