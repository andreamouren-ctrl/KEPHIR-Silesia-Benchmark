#include "kephir2/auto_routing.hpp"

#include "kephir2/archive.hpp"
#include "kephir2/execution.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

namespace kephir2 {
namespace {

constexpr std::uint64_t kMinFileSample = 4096;
constexpr std::uint64_t kStrata = 4;

class TempProbeTree {
public:
    explicit TempProbeTree(std::filesystem::path path)
        : path_(std::move(path)) {}

    TempProbeTree(const TempProbeTree&) = delete;
    TempProbeTree& operator=(const TempProbeTree&) = delete;

    TempProbeTree(TempProbeTree&& other) noexcept
        : path_(std::move(other.path_)) {
        other.path_.clear();
    }

    TempProbeTree& operator=(TempProbeTree&& other) noexcept {
        if (this != &other) {
            cleanup();
            path_ = std::move(other.path_);
            other.path_.clear();
        }
        return *this;
    }

    ~TempProbeTree() {
        cleanup();
    }

    [[nodiscard]] const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    void cleanup() noexcept {
        if (path_.empty()) return;
        std::error_code ec;
        std::filesystem::remove_all(path_, ec);
    }

    std::filesystem::path path_;
};

std::filesystem::path unique_probe_path() {
    static std::atomic<std::uint64_t> sequence{0};
    const auto ticks = static_cast<std::uint64_t>(
        std::chrono::steady_clock::now().time_since_epoch().count());
    const auto id = sequence.fetch_add(1, std::memory_order_relaxed);
    return std::filesystem::temp_directory_path()
        / ("kephir2_probe_" + std::to_string(ticks) + "_" + std::to_string(id));
}

std::vector<std::uint8_t> read_window(
    const std::filesystem::path& path,
    std::uint64_t offset,
    std::uint64_t length) {

    if (length == 0) return {};

    if (length > static_cast<std::uint64_t>(
            std::numeric_limits<std::size_t>::max())) {
        throw std::runtime_error("probe window exceeds addressable memory");
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unable to open probe source file");

    in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!in) throw std::runtime_error("unable to seek probe source file");

    std::vector<std::uint8_t> out(static_cast<std::size_t>(length));
    in.read(
        reinterpret_cast<char*>(out.data()),
        static_cast<std::streamsize>(out.size()));

    const auto got = static_cast<std::size_t>(in.gcount());
    out.resize(got);
    return out;
}

std::vector<std::uint8_t> stratified_sample(
    const std::filesystem::path& path,
    std::uint64_t budget) {

    const auto size = std::filesystem::file_size(path);

    if (size <= budget) {
        return read_window(path, 0, size);
    }
    if (budget == 0) {
        return {};
    }

    const auto parts = std::min<std::uint64_t>(
        kStrata,
        std::max<std::uint64_t>(1, budget / kMinFileSample));
    const auto part = std::max<std::uint64_t>(1, budget / parts);
    const auto max_offset = size > part ? size - part : 0;

    std::vector<std::uint64_t> offsets;
    offsets.reserve(static_cast<std::size_t>(parts));

    if (parts == 1) {
        offsets.push_back(max_offset / 2);
    } else {
        for (std::uint64_t i = 0; i < parts; ++i) {
            offsets.push_back((max_offset * i) / (parts - 1));
        }
    }

    std::vector<std::uint8_t> out;
    out.reserve(static_cast<std::size_t>(budget));

    std::uint64_t previous = std::numeric_limits<std::uint64_t>::max();
    for (const auto offset : offsets) {
        if (offset == previous) continue;
        previous = offset;

        const auto remaining = budget - out.size();
        if (remaining == 0) break;

        const auto want = std::min(part, remaining);
        auto window = read_window(path, offset, want);
        out.insert(out.end(), window.begin(), window.end());
    }

    if (out.size() > budget) {
        out.resize(static_cast<std::size_t>(budget));
    }
    return out;
}

std::vector<std::uint64_t> choose_file_budgets(
    const std::vector<std::filesystem::path>& files,
    std::uint64_t total_budget) {

    std::vector<std::uint64_t> sizes;
    sizes.reserve(files.size());

    std::uint64_t total = 0;
    for (const auto& path : files) {
        const auto size = std::filesystem::file_size(path);
        sizes.push_back(size);
        total += size;
    }

    if (total <= total_budget) {
        return sizes;
    }

    const auto n = std::max<std::uint64_t>(1, files.size());
    const auto base = std::max<std::uint64_t>(
        kMinFileSample,
        total_budget / n);

    std::vector<std::uint64_t> budgets(sizes.size(), 0);
    std::uint64_t used = 0;

    for (std::size_t i = 0; i < sizes.size(); ++i) {
        budgets[i] = std::min(sizes[i], base);
        used += budgets[i];
    }

    std::uint64_t remain = used < total_budget ? total_budget - used : 0;

    while (remain > 0) {
        std::vector<std::size_t> eligible;
        for (std::size_t i = 0; i < sizes.size(); ++i) {
            if (budgets[i] < sizes[i]) eligible.push_back(i);
        }

        if (eligible.empty()) break;

        const auto share = std::max<std::uint64_t>(
            1,
            remain / eligible.size());

        std::uint64_t progressed = 0;
        for (const auto i : eligible) {
            const auto capacity = sizes[i] - budgets[i];
            const auto add = std::min({
                share,
                capacity,
                remain
            });
            if (add == 0) continue;

            budgets[i] += add;
            remain -= add;
            progressed += add;

            if (remain == 0) break;
        }

        if (progressed == 0) break;
    }

    const auto sum_budgets = [&]() {
        std::uint64_t sum = 0;
        for (const auto value : budgets) sum += value;
        return sum;
    };

    auto current = sum_budgets();
    std::uint64_t over = current > total_budget
        ? current - total_budget
        : 0;

    if (over > 0) {
        for (std::size_t rev = budgets.size(); rev > 0 && over > 0; --rev) {
            const auto i = rev - 1;
            const auto minimum = std::min<std::uint64_t>(sizes[i], 1);
            const auto reducible = budgets[i] > minimum
                ? budgets[i] - minimum
                : 0;
            const auto cut = std::min(reducible, over);
            budgets[i] -= cut;
            over -= cut;
        }
    }

    return budgets;
}

struct ProbeTreeResult {
    TempProbeTree tree;
    std::uint64_t sampled_bytes{0};
};

ProbeTreeResult make_probe_tree(
    const std::filesystem::path& root,
    std::uint64_t budget) {

    const auto files = collect_directory_files(root);
    const auto budgets = choose_file_budgets(files, budget);

    const auto destination = unique_probe_path();
    std::filesystem::create_directories(destination);

    std::uint64_t sampled = 0;

    try {
        for (std::size_t i = 0; i < files.size(); ++i) {
            const auto relative = files[i].lexically_relative(root);
            const auto target = destination / relative;
            std::filesystem::create_directories(target.parent_path());

            auto data = stratified_sample(files[i], budgets[i]);

            std::ofstream out(target, std::ios::binary | std::ios::trunc);
            if (!out) throw std::runtime_error("unable to create probe sample file");

            if (!data.empty()) {
                out.write(
                    reinterpret_cast<const char*>(data.data()),
                    static_cast<std::streamsize>(data.size()));
                if (!out) throw std::runtime_error("unable to write probe sample file");
            }

            sampled += data.size();
        }
    } catch (...) {
        std::error_code ec;
        std::filesystem::remove_all(destination, ec);
        throw;
    }

    return {
        TempProbeTree(destination),
        sampled
    };
}

LayoutProbe measure_probe(
    const std::filesystem::path& root,
    std::uint64_t budget,
    CompressionBackend& backend,
    const BackendOptions& backend_options) {

    auto sample = make_probe_tree(root, budget);

    BackendOptions probe_options = backend_options;
    probe_options.allow_local_experience = false;

    ArchiveExecutor executor;

    const auto start = std::chrono::steady_clock::now();

    const auto flat = executor.compress_directory(
        sample.tree.path(),
        backend,
        probe_options,
        Layout::Flat);

    const auto smart = executor.compress_directory(
        sample.tree.path(),
        backend,
        probe_options,
        Layout::Smart);

    const auto end = std::chrono::steady_clock::now();

    LayoutProbe probe;
    probe.sampled_bytes = sample.sampled_bytes;
    probe.flat_archive_bytes = flat.size();
    probe.smart_archive_bytes = smart.size();
    probe.elapsed_seconds =
        std::chrono::duration<double>(end - start).count();
    return probe;
}

} // namespace

ResolvedDirectoryStrategy ProductionAutoResolver::resolve(
    const std::filesystem::path& root,
    CompressionBackend& backend,
    Profile profile,
    const BackendOptions& backend_options,
    const AnalyzerOptions& analyzer_options) const {

    CompressionPlanner planner;
    GlobalRouter router;

    auto initial = planner.plan_directory(
        root,
        profile,
        std::nullopt,
        analyzer_options);

    ResolvedDirectoryStrategy out;
    out.features = initial.features;
    out.strategy = initial.strategy;

    std::size_t safety = 0;
    while (out.strategy.requested_probe_bytes != 0) {
        if (++safety > 2) {
            throw std::runtime_error("AUTO routing requested too many probe stages");
        }

        const auto target = static_cast<std::uint64_t>(
            out.strategy.requested_probe_bytes);

        auto probe = measure_probe(
            root,
            target,
            backend,
            backend_options);

        if (!probe.valid()) {
            throw std::runtime_error("AUTO routing produced an invalid layout probe");
        }

        if (!out.probes.empty()
            && probe.sampled_bytes <= out.probes.back().sampled_bytes) {
            throw std::runtime_error("AUTO routing probe did not increase coverage");
        }

        out.probes.push_back(probe);
        out.strategy = router.plan(
            out.features,
            profile,
            out.probes.back());
    }

    return out;
}

} // namespace kephir2
