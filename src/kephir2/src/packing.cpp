#include "kephir2/packing.hpp"

#include <algorithm>
#include <fstream>
#include <limits>
#include <map>
#include <set>
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

PackedGroupSource::PackedGroupSource(
    std::filesystem::path root,
    const DirectoryPackingPlan& plan,
    std::size_t group_index)
    : root_(std::move(root)) {

    if (group_index >= plan.groups.size()) {
        throw std::out_of_range("packing group index out of range");
    }

    const auto& group = plan.groups[group_index];
    size_ = group.raw_length;
    segments_.reserve(group.file_indices.size());

    for (const auto file_index : group.file_indices) {
        if (file_index >= plan.files.size()) {
            throw std::runtime_error("packing plan contains invalid file index");
        }

        const auto& file = plan.files[file_index];
        if (file.group_id != group_index) {
            throw std::runtime_error("packing plan group/file mismatch");
        }

        segments_.push_back({
            std::filesystem::u8path(file.path.begin(), file.path.end()),
            file.group_offset,
            file.size
        });
    }
}

std::uint64_t PackedGroupSource::size() const noexcept {
    return size_;
}

std::size_t PackedGroupSource::read(
    std::uint64_t offset,
    std::span<std::uint8_t> destination) const {

    if (destination.empty() || offset >= size_) {
        return 0;
    }

    const auto remaining_total = size_ - offset;
    const auto target = static_cast<std::size_t>(
        std::min<std::uint64_t>(remaining_total, destination.size()));

    std::size_t written = 0;
    const std::uint64_t request_end = offset + target;

    for (const auto& segment : segments_) {
        const std::uint64_t segment_begin = segment.logical_offset;
        const std::uint64_t segment_end = segment.logical_offset + segment.size;

        if (segment_end <= offset) {
            continue;
        }
        if (segment_begin >= request_end) {
            break;
        }

        const std::uint64_t copy_begin = std::max(offset, segment_begin);
        const std::uint64_t copy_end = std::min(request_end, segment_end);
        if (copy_end <= copy_begin) {
            continue;
        }

        const auto local_offset = copy_begin - segment_begin;
        const auto bytes = static_cast<std::size_t>(copy_end - copy_begin);

        std::ifstream in(root_ / segment.relative_path, std::ios::binary);
        if (!in) {
            throw std::runtime_error("unable to open packed group source file");
        }

        in.seekg(static_cast<std::streamoff>(local_offset), std::ios::beg);
        if (!in) {
            throw std::runtime_error("unable to seek packed group source file");
        }

        in.read(
            reinterpret_cast<char*>(destination.data() + written),
            static_cast<std::streamsize>(bytes));

        if (in.gcount() != static_cast<std::streamsize>(bytes)) {
            throw std::runtime_error("short read from packed group source file");
        }

        written += bytes;
        if (written == target) {
            break;
        }
    }

    if (written != target) {
        throw std::runtime_error("packed group source logical range is incomplete");
    }

    return written;
}

PackedGroupSink::PackedGroupSink(
    std::filesystem::path root,
    std::span<const ManifestRecord> records,
    std::uint64_t group_id,
    std::uint64_t expected_raw_length)
    : size_(expected_raw_length) {

    std::filesystem::create_directories(root);

    std::uint64_t cursor = 0;
    std::set<std::filesystem::path> seen_targets;

    for (const auto& record : records) {
        if (record.group_id != group_id) {
            continue;
        }

        if (record.size > std::numeric_limits<std::uint64_t>::max() - cursor) {
            throw std::runtime_error("extraction group raw length overflow");
        }

        const auto target = safe_archive_target(root, record.path);
        if (!seen_targets.insert(target).second) {
            throw std::runtime_error("duplicate archive output path");
        }

        std::filesystem::create_directories(target.parent_path());

        {
            std::ofstream out(target, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("unable to create extraction target");
            }
        }

        std::error_code ec;
        std::filesystem::resize_file(target, record.size, ec);
        if (ec) {
            throw std::runtime_error("unable to size extraction target");
        }

        segments_.push_back({target, cursor, record.size});
        cursor += record.size;
    }

    if (cursor != expected_raw_length) {
        throw std::runtime_error("extraction group raw length mismatch");
    }
}

void PackedGroupSink::write(
    std::uint64_t offset,
    std::span<const std::uint8_t> source) {

    if (source.empty()) {
        if (offset > size_) {
            throw std::out_of_range("extraction sink write offset out of range");
        }
        return;
    }

    if (offset >= size_ || source.size() > size_ - offset) {
        throw std::out_of_range("extraction sink write range out of bounds");
    }

    std::size_t consumed = 0;
    const std::uint64_t request_end = offset + source.size();

    for (const auto& segment : segments_) {
        const std::uint64_t segment_begin = segment.logical_offset;
        const std::uint64_t segment_end = segment.logical_offset + segment.size;

        if (segment_end <= offset) {
            continue;
        }
        if (segment_begin >= request_end) {
            break;
        }

        const std::uint64_t write_begin = std::max(offset, segment_begin);
        const std::uint64_t write_end = std::min(request_end, segment_end);
        if (write_end <= write_begin) {
            continue;
        }

        const auto local_offset = write_begin - segment_begin;
        const auto bytes = static_cast<std::size_t>(write_end - write_begin);

        std::fstream out(
            segment.target_path,
            std::ios::binary | std::ios::in | std::ios::out);
        if (!out) {
            throw std::runtime_error("unable to open extraction target for write");
        }

        out.seekp(static_cast<std::streamoff>(local_offset), std::ios::beg);
        if (!out) {
            throw std::runtime_error("unable to seek extraction target");
        }

        out.write(
            reinterpret_cast<const char*>(source.data() + consumed),
            static_cast<std::streamsize>(bytes));
        if (!out) {
            throw std::runtime_error("unable to write extraction target");
        }

        consumed += bytes;
        if (consumed == source.size()) {
            break;
        }
    }

    if (consumed != source.size()) {
        throw std::runtime_error("extraction sink logical range is incomplete");
    }
}

std::uint64_t PackedGroupSink::size() const noexcept {
    return size_;
}

} // namespace kephir2
