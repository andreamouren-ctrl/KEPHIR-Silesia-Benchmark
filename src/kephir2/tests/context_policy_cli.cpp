#include "kephir2/context_policy.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

class FileSource final : public kephir2::ByteSource {
public:
    explicit FileSource(std::filesystem::path path)
        : path_(std::move(path)),
          size_(std::filesystem::file_size(path_)) {}

    std::uint64_t size() const noexcept override {
        return size_;
    }

    std::size_t read(
        std::uint64_t offset,
        std::span<std::uint8_t> destination) const override {

        if (destination.empty() || offset >= size_) return 0;

        const auto count = static_cast<std::size_t>(
            std::min<std::uint64_t>(
                destination.size(),
                size_ - offset));

        std::ifstream in(path_, std::ios::binary);
        if (!in) throw std::runtime_error("cannot open input");

        in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!in) throw std::runtime_error("cannot seek input");

        in.read(
            reinterpret_cast<char*>(destination.data()),
            static_cast<std::streamsize>(count));
        if (in.gcount() != static_cast<std::streamsize>(count)) {
            throw std::runtime_error("short input read");
        }
        return count;
    }

private:
    std::filesystem::path path_;
    std::uint64_t size_{0};
};

const char* context_name(std::size_t bytes) {
    if (bytes == 512u * 1024u) return "baseline";
    if (bytes == 4u * 1024u * 1024u) return "ctx4m";
    if (bytes == 8u * 1024u * 1024u) return "ctx8m";
    return "other";
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: kephir2_context_policy_cli <input-file>\n";
        return 2;
    }

    try {
        const std::filesystem::path path = argv[1];
        FileSource source(path);
        const auto decision = kephir2::choose_adaptive_context(source);

        std::cout
            << "FILE=" << path.filename().string() << "\n"
            << "RAW_BYTES=" << source.size() << "\n"
            << "SAMPLED_BYTES=" << decision.sampled_bytes << "\n"
            << "SPREAD=" << decision.quarter_entropy_spread << "\n"
            << "PARENT_BYTES=" << decision.parent_bytes << "\n"
            << "INNER_BYTES=" << decision.inner_chunk_bytes << "\n"
            << "DECISION=" << context_name(decision.inner_chunk_bytes) << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
