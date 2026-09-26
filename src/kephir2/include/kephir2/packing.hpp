#pragma once

#include "kephir2/analyzer.hpp"
#include "kephir2/archive.hpp"
#include "kephir2/backend.hpp"

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

class PackedGroupSource final : public ByteSource {
public:
    PackedGroupSource(
        std::filesystem::path root,
        const DirectoryPackingPlan& plan,
        std::size_t group_index);

    [[nodiscard]] std::uint64_t size() const noexcept override;

    [[nodiscard]] std::size_t read(
        std::uint64_t offset,
        std::span<std::uint8_t> destination) const override;

private:
    struct Segment {
        std::filesystem::path relative_path;
        std::uint64_t logical_offset{0};
        std::uint64_t size{0};
    };

    std::filesystem::path root_;
    std::uint64_t size_{0};
    std::vector<Segment> segments_;
};

class PackedGroupSink final : public ByteSink {
public:
    PackedGroupSink(
        std::filesystem::path root,
        std::span<const ManifestRecord> records,
        std::uint64_t group_id,
        std::uint64_t expected_raw_length);

    void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) override;

    [[nodiscard]] std::uint64_t size() const noexcept;

private:
    struct Segment {
        std::filesystem::path target_path;
        std::uint64_t logical_offset{0};
        std::uint64_t size{0};
    };

    std::uint64_t size_{0};
    std::vector<Segment> segments_;
};

} // namespace kephir2
