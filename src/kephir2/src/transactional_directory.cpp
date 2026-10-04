#include "kephir2/transactional_directory.hpp"

#include <chrono>
#include <stdexcept>
#include <string>
#include <system_error>

namespace kephir2 {
namespace {

using Clock = std::chrono::steady_clock;

std::filesystem::path sibling_unique_path(
    const std::filesystem::path& destination,
    std::string_view role) {

    const auto ticks = static_cast<unsigned long long>(
        Clock::now().time_since_epoch().count());
    auto parent = destination.parent_path();
    if (parent.empty()) parent = ".";
    return parent / (
        destination.filename().string()
        + "."
        + std::string(role)
        + "."
        + std::to_string(ticks));
}

void ensure_directory_or_absent(const std::filesystem::path& path) {
    if (!std::filesystem::exists(path)) return;
    if (!std::filesystem::is_directory(path)) {
        throw std::runtime_error("transactional extraction destination is not a directory");
    }
}

void reject_symlinks(const std::filesystem::path& root) {
    if (!std::filesystem::exists(root)) return;
    const auto root_status = std::filesystem::symlink_status(root);
    if (std::filesystem::is_symlink(root_status)) {
        throw std::runtime_error("transactional extraction destination contains unsupported symlink");
    }
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_symlink()) {
            throw std::runtime_error("transactional extraction destination contains unsupported symlink");
        }
    }
}

} // namespace

std::filesystem::path make_directory_stage_path(
    const std::filesystem::path& destination,
    std::string_view role) {

    return sibling_unique_path(destination, role);
}

void remove_directory_tree_noexcept(
    const std::filesystem::path& path) noexcept {

    if (path.empty()) return;
    std::error_code ec;
    std::filesystem::remove_all(path, ec);
}

void prepare_directory_stage(
    const std::filesystem::path& stage,
    const std::filesystem::path& destination,
    bool clone_existing) {

    if (stage.empty() || destination.empty() || stage == destination) {
        throw std::invalid_argument("invalid transactional extraction stage path");
    }

    ensure_directory_or_absent(destination);
    remove_directory_tree_noexcept(stage);

    const auto parent = stage.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }

    if (clone_existing && std::filesystem::exists(destination)) {
        reject_symlinks(destination);
        std::filesystem::copy(
            destination,
            stage,
            std::filesystem::copy_options::recursive
                | std::filesystem::copy_options::overwrite_existing);
        if (!std::filesystem::is_directory(stage)) {
            throw std::runtime_error("unable to clone transactional extraction destination");
        }
        return;
    }

    std::filesystem::create_directories(stage);
}

void publish_directory_stage(
    const std::filesystem::path& stage,
    const std::filesystem::path& destination,
    bool allow_replace) {

    if (stage.empty() || destination.empty() || stage == destination) {
        throw std::invalid_argument("invalid transactional extraction publication path");
    }
    if (!std::filesystem::is_directory(stage)) {
        throw std::runtime_error("transactional extraction stage does not exist");
    }

    const bool destination_exists = std::filesystem::exists(destination);
    if (!destination_exists) {
        std::filesystem::rename(stage, destination);
        return;
    }
    if (!allow_replace) {
        throw std::runtime_error("output directory already exists");
    }
    ensure_directory_or_absent(destination);

    const auto backup = sibling_unique_path(destination, "aur2-backup");
    remove_directory_tree_noexcept(backup);

    std::filesystem::rename(destination, backup);
    try {
        std::filesystem::rename(stage, destination);
    } catch (...) {
        std::error_code restore_ec;
        if (!std::filesystem::exists(destination)) {
            std::filesystem::rename(backup, destination, restore_ec);
        }
        throw;
    }

    remove_directory_tree_noexcept(backup);
}

} // namespace kephir2
