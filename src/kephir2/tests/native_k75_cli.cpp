#include "kephir2/execution.hpp"
#include "kephir2/native_k75.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <cstdlib>
#include <vector>

namespace {

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open input");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& data) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create output");
    out.write(
        reinterpret_cast<const char*>(data.data()),
        static_cast<std::streamsize>(data.size()));
    if (!out) throw std::runtime_error("cannot write output");
}

} // namespace

int main(int argc, char** argv) {
    using namespace kephir2;

    if (argc < 4) {
        std::cerr
            << "usage:\n"
            << "  kephir2_native_k75_cli c <input-file> <archive.kpf> [workers]\n"
            << "  kephir2_native_k75_cli d <archive.kpf> <output-dir> [workers]\n";
        return 2;
    }

    try {
        const std::string mode = argv[1];
        const std::filesystem::path input = argv[2];
        const std::filesystem::path output = argv[3];

        NativeK75Backend backend;
        ArchiveExecutor executor;

        BackendOptions backend_options{};
        backend_options.workers = 1;
        if (argc >= 5) {
            const auto parsed = std::strtoul(argv[4], nullptr, 10);
            if (parsed == 0 || parsed > 64) {
                throw std::runtime_error("invalid worker count");
            }
            backend_options.workers = static_cast<std::size_t>(parsed);
        }

        const auto t0 = std::chrono::steady_clock::now();

        if (mode == "c") {
            const auto archive =
                executor.compress_file(input, backend, backend_options);
            write_all(output, archive);

            const auto t1 = std::chrono::steady_clock::now();
            std::cout
                << "MODE=c\n"
                << "INPUT_BYTES=" << std::filesystem::file_size(input) << "\n"
                << "OUTPUT_BYTES=" << archive.size() << "\n"
                << "WORKERS=" << backend_options.workers << "\n"
                << "SECONDS="
                << std::chrono::duration<double>(t1 - t0).count()
                << "\n";
            return 0;
        }

        if (mode == "d") {
            const auto archive = read_all(input);
            executor.extract_file(
                archive,
                output,
                backend,
                backend_options);

            const auto t1 = std::chrono::steady_clock::now();
            std::cout
                << "MODE=d\n"
                << "INPUT_BYTES=" << archive.size() << "\n"
                << "WORKERS=" << backend_options.workers << "\n"
                << "SECONDS="
                << std::chrono::duration<double>(t1 - t0).count()
                << "\n";
            return 0;
        }

        std::cerr << "unknown mode\n";
        return 2;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
