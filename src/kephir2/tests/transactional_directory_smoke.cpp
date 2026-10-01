#include "kephir2/transactional_directory.hpp"

#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void write_text(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to write transactional fixture");
    out << text;
    require(static_cast<bool>(out), "unable to persist transactional fixture");
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(static_cast<bool>(in), "unable to read transactional fixture");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2;

    const auto root = fs::temp_directory_path() / "kephir2_transactional_directory_smoke";
    const auto fresh = root / "fresh";
    const auto existing = root / "existing";
    fs::remove_all(root);
    fs::create_directories(root);

    // Fresh destination: build entirely in staging, then publish by rename.
    const auto fresh_stage = make_directory_stage_path(fresh, "aur2-stage");
    prepare_directory_stage(fresh_stage, fresh, false);
    write_text(fresh_stage / "new.txt", "fresh payload");
    publish_directory_stage(fresh_stage, fresh, false);
    require(read_text(fresh / "new.txt") == "fresh payload",
            "fresh transactional publication mismatch");
    require(!fs::exists(fresh_stage), "fresh stage survived publication");

    // Existing destination: clone first so unrelated files survive an overwrite.
    fs::create_directories(existing);
    write_text(existing / "keep.txt", "preserve me");
    write_text(existing / "replace.txt", "old value");

    const auto overwrite_stage = make_directory_stage_path(existing, "aur2-stage");
    prepare_directory_stage(overwrite_stage, existing, true);
    require(read_text(overwrite_stage / "keep.txt") == "preserve me",
            "existing tree was not cloned into transactional stage");
    write_text(overwrite_stage / "replace.txt", "new value");
    write_text(overwrite_stage / "added.txt", "added value");
    publish_directory_stage(overwrite_stage, existing, true);

    require(read_text(existing / "keep.txt") == "preserve me",
            "transactional overwrite lost unrelated existing file");
    require(read_text(existing / "replace.txt") == "new value",
            "transactional overwrite did not replace target file");
    require(read_text(existing / "added.txt") == "added value",
            "transactional overwrite did not publish added file");
    require(!fs::exists(overwrite_stage), "overwrite stage survived publication");

    // Replacement denied: destination and stage must both remain untouched.
    const auto denied_stage = make_directory_stage_path(existing, "denied-stage");
    prepare_directory_stage(denied_stage, existing, false);
    write_text(denied_stage / "candidate.txt", "candidate");

    bool denied = false;
    try {
        publish_directory_stage(denied_stage, existing, false);
    } catch (const std::exception&) {
        denied = true;
    }
    require(denied, "transactional publish ignored replacement policy");
    require(read_text(existing / "keep.txt") == "preserve me",
            "denied transactional publish changed destination");
    require(read_text(denied_stage / "candidate.txt") == "candidate",
            "denied transactional publish destroyed stage");

    remove_directory_tree_noexcept(denied_stage);
    fs::remove_all(root);
    return 0;
}
