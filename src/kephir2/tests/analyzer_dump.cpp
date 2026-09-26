#include "kephir2/analyzer.hpp"

#include <filesystem>
#include <iomanip>\n#include <iostream>

int main(int argc, char** argv) {
    using namespace kephir2;

    if (argc < 2) {
        std::cerr << "usage: kephir2_analyzer_dump FILE...\n";
        return 2;
    }

    std::cout << std::setprecision(17);\n\n    ContentAnalyzer analyzer;
    for (int i = 1; i < argc; ++i) {
        const std::filesystem::path path(argv[i]);
        try {
            const auto r = analyzer.analyze_file(path);
            std::cout << path.generic_string() << '\t'
                      << to_string(r.content_class) << '\t'
                      << r.metrics.original_bytes << '\t'
                      << r.metrics.sampled_bytes << '\t'
                      << r.metrics.entropy << '\t'
                      << r.metrics.printable_fraction << '\t'
                      << r.metrics.zero_fraction << '\n';
        } catch (const std::exception& e) {
            std::cerr << path.generic_string() << ": " << e.what() << '\n';
            return 1;
        }
    }

    return 0;
}
