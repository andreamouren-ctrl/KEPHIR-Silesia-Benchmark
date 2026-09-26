#include "kephir2/archive.hpp"
#include "kephir2/execution.hpp"
#include "kephir2/native_k75.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open input file");
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
    if (!out) throw std::runtime_error("cannot create output file");
    out.write(
        reinterpret_cast<const char*>(data.data()),
        static_cast<std::streamsize>(data.size()));
    if (!out) throw std::runtime_error("cannot write output file");
}

} // namespace

int main(int argc, char** argv) {
    using namespace kephir2;

    if (argc != 4) {
        std::cerr
            << "usage: kephir2_interop_tool compress INPUT OUTPUT\n"
            << "       kephir2_interop_tool extract ARCHIVE OUTPUT_DIR\n";
        return 2;
    }

    try {
        const std::string mode = argv[1];
        const std::filesystem::path input = argv[2];
        const std::filesystem::path output = argv[3];

        NativeK75Backend backend;
        ArchiveExecutor executor;
        BackendOptions options{};
        options.workers = 1;
        options.allow_local_experience = false;

        if (mode == "compress") {
            const auto archive = std::filesystem::is_directory(input)
                ? executor.compress_directory(
                    input,
                    backend,
                    options,
                    Layout::Smart)
                : executor.compress_file(
                    input,
                    backend,
                    options);

            write_all(output, archive);
            std::cout << "NATIVE_COMPRESS_OK " << archive.size() << "\n";
            return 0;
        }

        if (mode == "extract") {
            const auto archive = read_all(input);
            if (archive.size() < 5
                || archive[0] != 'K'
                || archive[1] != 'P'
                || archive[2] != 'F'
                || archive[3] != '1') {
                throw std::runtime_error("not KPF1");
            }

            if (archive[4] == static_cast<std::uint8_t>(Kpf1Kind::File)) {
                executor.extract_file(archive, output, backend, options);
            } else if (
                archive[4] == static_cast<std::uint8_t>(Kpf1Kind::Directory)) {
                executor.extract_directory(archive, output, backend, options);
            } else {
                throw std::runtime_error("unknown KPF1 kind");
            }

            std::cout << "NATIVE_EXTRACT_OK\n";
            return 0;
        }

        std::cerr << "invalid mode\n";
        return 2;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
