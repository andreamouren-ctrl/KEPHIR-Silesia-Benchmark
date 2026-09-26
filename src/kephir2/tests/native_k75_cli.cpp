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
            << "  kephir2_native_k75_cli c <input-file> <archive.kpf> [workers] [context-kib]\n"
            << "  kephir2_native_k75_cli c <input-file> <archive.kpf> [workers] <parent-kib> <inner-kib> [force-parent-grain]\n"
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

        std::size_t research_context_kib = 0;
        std::size_t research_parent_kib = 0;
        std::size_t research_inner_kib = 0;
        bool research_force_parent_grain = false;

        if (mode == "c" && argc >= 6) {
            const auto parsed = std::strtoul(argv[5], nullptr, 10);
            if (parsed < 128 || parsed > 8192) {
                throw std::runtime_error("invalid research parent/context KiB");
            }

            if (argc >= 7) {
                const auto inner = std::strtoul(argv[6], nullptr, 10);
                if (inner < 128 || inner > 8192) {
                    throw std::runtime_error("invalid research inner KiB");
                }

                research_parent_kib = static_cast<std::size_t>(parsed);
                research_inner_kib = static_cast<std::size_t>(inner);
                research_force_parent_grain =
                    argc >= 8 ? std::strtoul(argv[7], nullptr, 10) != 0 : true;

                backend_options.research_parent_bytes =
                    research_parent_kib * 1024u;
                backend_options.research_inner_chunk_bytes =
                    research_inner_kib * 1024u;
                backend_options.research_force_parent_grain =
                    research_force_parent_grain;
            } else {
                // Backward-compatible EXP-109 behavior.
                research_context_kib = static_cast<std::size_t>(parsed);
                const auto bytes = research_context_kib * 1024u;
                backend_options.research_parent_bytes = bytes;
                backend_options.research_inner_chunk_bytes = bytes;
                backend_options.research_force_parent_grain = true;
            }
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
                << "CONTEXT_KIB=" << research_context_kib << "\n"
                << "PARENT_KIB=" << research_parent_kib << "\n"
                << "INNER_KIB=" << research_inner_kib << "\n"
                << "FORCE_PARENT_GRAIN=" << (research_force_parent_grain ? 1 : 0) << "\n"
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
