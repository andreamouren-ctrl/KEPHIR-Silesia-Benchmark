#include "kephir2/native37_blob.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
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

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create output");
    out.write(
        reinterpret_cast<const char*>(data.data()),
        static_cast<std::streamsize>(data.size()));
    if (!out) throw std::runtime_error("cannot write output");
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr
            << "usage: kephir2_native37_blob_cli <input> <output.aur>\n";
        return 2;
    }

    try {
        const auto raw = read_all(argv[1]);
        const auto blob = kephir2::native37::encode_aur2_blob(raw);
        write_all(argv[2], blob);
        std::cout
            << "RAW_BYTES=" << raw.size() << "\n"
            << "AUR2_BYTES=" << blob.size() << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
