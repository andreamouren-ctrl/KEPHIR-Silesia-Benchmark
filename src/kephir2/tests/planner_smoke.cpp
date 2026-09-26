#include "kephir2/planner.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>

int main() {
    using namespace kephir2;

    const auto root = std::filesystem::temp_directory_path() / "kephir2_planner_smoke";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root / "sub");

    const std::string text =
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n"
        "struct Node{int x;int y;};\n";

    {
        std::ofstream f(root / "a.dat", std::ios::binary);
        for (int i = 0; i < 256; ++i) {
            f << text;
        }
    }

    {
        std::ofstream f(root / "sub" / "b.dat", std::ios::binary);
        for (int i = 0; i < 8192; ++i) {
            const char v = static_cast<char>(i & 0xff);
            f.write(&v, 1);
        }
    }

    CompressionPlanner planner;

    const auto preliminary = planner.plan_directory(root, Profile::Auto);
    assert(preliminary.features.file_count == 2);
    assert(preliminary.features.logical_bytes > 0);
    assert(preliminary.strategy.require_integrity_verification);

    LayoutProbe exact_probe{};
    exact_probe.sampled_bytes = preliminary.features.logical_bytes;
    exact_probe.flat_archive_bytes = 1000;
    exact_probe.smart_archive_bytes = 1100;

    const auto planned = planner.plan_directory(root, Profile::Auto, exact_probe);
    assert(planned.strategy.layout == Layout::Flat);
    assert(!planned.strategy.request_extended_probe);

    std::filesystem::remove_all(root);
    return 0;
}
