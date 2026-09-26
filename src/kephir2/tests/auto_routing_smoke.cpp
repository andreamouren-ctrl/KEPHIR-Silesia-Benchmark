#include "kephir2/auto_routing.hpp"
#include "kephir2/native_k75.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>

namespace {

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    std::size_t written = 0;
    while (written < size) {
        const auto n = std::min(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        written += n;
    }
}

} // namespace

int main() {
    using namespace kephir2;

    const auto base =
        std::filesystem::temp_directory_path() / "kephir2_auto_routing_smoke";
    const auto homogeneous = base / "homogeneous";
    const auto heterogeneous = base / "heterogeneous";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(homogeneous);
    std::filesystem::create_directories(heterogeneous);

    for (int i = 0; i < 4; ++i) {
        write_repeat(
            homogeneous / ("f" + std::to_string(i) + ".dat"),
            "ordinary prose words and spaces form a natural sentence.\n",
            256u * 1024u);
    }

    write_repeat(
        heterogeneous / "code0.dat",
        "int f(int x){return x*x+17;}\n",
        640u * 1024u);
    write_repeat(
        heterogeneous / "code1.dat",
        "int g(int x){return x+31;}\n",
        640u * 1024u);

    {
        std::ofstream a(heterogeneous / "zero0.dat", std::ios::binary);
        std::ofstream b(heterogeneous / "zero1.dat", std::ios::binary);
        for (std::size_t i = 0; i < 640u * 1024u / 4u; ++i) {
            const char bytes[4] = {0, 0, static_cast<char>(i & 0xff), 0};
            a.write(bytes, 4);
            b.write(bytes, 4);
        }
    }

    NativeK75Backend backend;
    ProductionAutoResolver resolver;

    const auto one_class = resolver.resolve(
        homogeneous,
        backend,
        Profile::Auto);

    assert(one_class.strategy.layout == Layout::Flat);
    assert(one_class.strategy.requested_probe_bytes == 0);
    assert(one_class.probes.empty());

    const auto mixed = resolver.resolve(
        heterogeneous,
        backend,
        Profile::Auto);

    assert(mixed.strategy.layout == Layout::Flat
        || mixed.strategy.layout == Layout::Smart);
    assert(mixed.strategy.requested_probe_bytes == 0);
    assert(!mixed.probes.empty());
    assert(mixed.probes.size() <= 2);

    for (const auto& probe : mixed.probes) {
        assert(probe.valid());
        assert(probe.sampled_bytes > 0);
        assert(probe.flat_archive_bytes > 0);
        assert(probe.smart_archive_bytes > 0);
    }

    std::filesystem::remove_all(base);
    return 0;
}
