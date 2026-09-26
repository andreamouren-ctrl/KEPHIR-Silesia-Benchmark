#include "kephir2/auto_routing.hpp"
#include "kephir2/execution.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace {

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& data) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create archive output");
    out.write(
        reinterpret_cast<const char*>(data.data()),
        static_cast<std::streamsize>(data.size()));
    if (!out) throw std::runtime_error("cannot write archive output");
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read file");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::vector<std::filesystem::path> list_files(
    const std::filesystem::path& root) {

    std::vector<std::filesystem::path> out;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_regular_file() && !entry.is_symlink()) {
            out.push_back(entry.path().lexically_relative(root));
        }
    }
    std::sort(out.begin(), out.end());
    return out;
}

bool compare_trees(
    const std::filesystem::path& a,
    const std::filesystem::path& b) {

    const auto af = list_files(a);
    const auto bf = list_files(b);
    if (af != bf) return false;

    for (const auto& rel : af) {
        if (read_all(a / rel) != read_all(b / rel)) {
            return false;
        }
    }
    return true;
}

const char* layout_name(kephir2::Layout layout) {
    using kephir2::Layout;
    switch (layout) {
    case Layout::Flat: return "flat";
    case Layout::Smart: return "smart";
    case Layout::Hybrid: return "hybrid";
    }
    return "unknown";
}

} // namespace

int main(int argc, char** argv) {
    using namespace kephir2;

    if (argc != 3) {
        std::cerr
            << "usage: kephir2_production_layout_bench DIRECTORY OUTDIR\n";
        return 2;
    }

    try {
        const std::filesystem::path root = argv[1];
        const std::filesystem::path out = argv[2];

        std::filesystem::remove_all(out);
        std::filesystem::create_directories(out);

        NativeK75Backend backend;
        BackendOptions options{};
        options.allow_local_experience = false;

        ProductionAutoResolver resolver;
        ArchiveExecutor executor;

        const auto rt0 = std::chrono::steady_clock::now();
        const auto resolved = resolver.resolve(
            root,
            backend,
            Profile::Auto,
            options);
        const auto rt1 = std::chrono::steady_clock::now();

        const auto st0 = std::chrono::steady_clock::now();
        const auto smart = executor.compress_directory(
            root,
            backend,
            options,
            Layout::Smart);
        const auto st1 = std::chrono::steady_clock::now();

        const auto ft0 = std::chrono::steady_clock::now();
        const auto flat = executor.compress_directory(
            root,
            backend,
            options,
            Layout::Flat);
        const auto ft1 = std::chrono::steady_clock::now();

        write_all(out / "smart.kpf", smart);
        write_all(out / "flat.kpf", flat);

        const auto smart_extract = out / "smart_extract";
        const auto flat_extract = out / "flat_extract";

        const auto sd0 = std::chrono::steady_clock::now();
        executor.extract_directory(
            smart,
            smart_extract,
            backend,
            options);
        const auto sd1 = std::chrono::steady_clock::now();

        const auto fd0 = std::chrono::steady_clock::now();
        executor.extract_directory(
            flat,
            flat_extract,
            backend,
            options);
        const auto fd1 = std::chrono::steady_clock::now();

        const bool smart_ok = compare_trees(root, smart_extract);
        const bool flat_ok = compare_trees(root, flat_extract);

        const auto oracle =
            smart.size() < flat.size() ? Layout::Smart : Layout::Flat;
        const auto selected = resolved.strategy.layout;
        const auto selected_bytes =
            selected == Layout::Smart ? smart.size() : flat.size();
        const auto oracle_bytes =
            oracle == Layout::Smart ? smart.size() : flat.size();

        double probe_seconds = 0.0;
        for (const auto& probe : resolved.probes) {
            probe_seconds += probe.elapsed_seconds;
        }

        std::cout
            << "SELECTED=" << layout_name(selected) << "\n"
            << "ORACLE=" << layout_name(oracle) << "\n"
            << "SMART_BYTES=" << smart.size() << "\n"
            << "FLAT_BYTES=" << flat.size() << "\n"
            << "REGRET_BYTES=" << (selected_bytes - oracle_bytes) << "\n"
            << "PROBE_COUNT=" << resolved.probes.size() << "\n"
            << "PROBE_SECONDS=" << probe_seconds << "\n"
            << "RESOLVE_SECONDS="
            << std::chrono::duration<double>(rt1 - rt0).count() << "\n"
            << "SMART_COMP_SECONDS="
            << std::chrono::duration<double>(st1 - st0).count() << "\n"
            << "FLAT_COMP_SECONDS="
            << std::chrono::duration<double>(ft1 - ft0).count() << "\n"
            << "SMART_DEC_SECONDS="
            << std::chrono::duration<double>(sd1 - sd0).count() << "\n"
            << "FLAT_DEC_SECONDS="
            << std::chrono::duration<double>(fd1 - fd0).count() << "\n"
            << "SMART_BYTE_PERFECT=" << (smart_ok ? 1 : 0) << "\n"
            << "FLAT_BYTE_PERFECT=" << (flat_ok ? 1 : 0) << "\n";

        return smart_ok && flat_ok ? 0 : 1;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
