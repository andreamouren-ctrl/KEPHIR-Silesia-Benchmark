#pragma once

#include <filesystem>
#include <string_view>

namespace kephir2 {

// Returns a unique sibling path on the same filesystem as destination so a
// completed extraction tree can be published with rename semantics.
[[nodiscard]] std::filesystem::path make_directory_stage_path(
    const std::filesystem::path& destination,
    std::string_view role);

// Creates a clean staging tree. When clone_existing is true and destination
// exists, the current directory tree is cloned into stage first so selective or
// overwrite extraction preserves unrelated pre-existing files until commit.
void prepare_directory_stage(
    const std::filesystem::path& stage,
    const std::filesystem::path& destination,
    bool clone_existing);

// Publishes a completed sibling stage. Existing destination content is first
// moved to a sibling backup and restored if the stage rename fails. On success
// the backup is deleted. allow_replace must be explicitly granted by the caller.
void publish_directory_stage(
    const std::filesystem::path& stage,
    const std::filesystem::path& destination,
    bool allow_replace);

void remove_directory_tree_noexcept(
    const std::filesystem::path& path) noexcept;

} // namespace kephir2
