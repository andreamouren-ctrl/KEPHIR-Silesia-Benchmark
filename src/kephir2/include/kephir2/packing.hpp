#pragma once

#include "kephir2/analyzer.hpp"
#include "kephir2/archive.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace kephir2 {

struct PackingFileRecord {
    std::string path;
    ContentClass content_class{ContentClass::Empty};
    std::string group_name;
    std::uint64_t group_id{0};
    std::uint64_t size{0};
    std::uint64_t group_offset{0};

    bool operator==(const PackingFileRecord&) const = default;
};

struct PackingGroup {
    std::string name;
    std::uint64_t raw_length{0};
    std::vector<std::size_t> file_indices;

    bool operator==(const PackingGroup&) const = default;
};

struct DirectoryPackingPlan {
    std::vector<PackingFileRecord> files;
    std::vector<PackingGroup> groups;
    ByteBuffer manifest;
};

[[nodiscard]] DirectoryPackingPlan build_directory_packing_plan(
    const std::filesystem::path& root,
    const ContentAnalyzer& analyzer = {});

} // namespace kephir2
