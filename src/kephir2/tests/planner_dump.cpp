#include "kephir2/planner.hpp"

#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string_view>

namespace {

std::string_view layout_name(kephir2::Layout layout) {
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

    if (argc < 2) {
        std::cerr << "usage: kephir2_planner_dump DIRECTORY...\n";
        return 2;
    }

    CompressionPlanner planner;
    std::cout << std::setprecision(17);

    for (int i = 1; i < argc; ++i) {
        const std::filesystem::path root(argv[i]);
        try {
            const auto t0 = std::chrono::steady_clock::now();
            const auto result = planner.plan_directory(root, Profile::Auto);
            const auto t1 = std::chrono::steady_clock::now();
            const double elapsed_ms =
                std::chrono::duration<double, std::milli>(t1 - t0).count();

            const auto& f = result.features;
            const auto& s = result.strategy;
            const char* action = s.request_initial_probe ? "probe" : "final";

            std::cout
                << root.generic_string() << '\t'
                << action << '\t'
                << layout_name(s.layout) << '\t'
                << s.requested_probe_bytes << '\t'
                << f.logical_bytes << '\t'
                << f.file_count << '\t'
                << f.sampled_content_groups << '\t'
                << f.multi_file_content_groups << '\t'
                << f.repeatable_content_byte_fraction << '\t'
                << f.sampled_dominant_byte_fraction << '\t'
                << f.average_file_bytes << '\t'
                << elapsed_ms << '\n';
        } catch (const std::exception& e) {
            std::cerr << root.generic_string() << ": " << e.what() << '\n';
            return 1;
        }
    }

    return 0;
}
