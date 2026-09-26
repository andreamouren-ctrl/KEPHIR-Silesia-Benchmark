#include "kephir2/execution.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

class IdentityBackend final : public kephir2::CompressionBackend {
public:
    const char* name() const noexcept override {
        return "identity-test";
    }

    std::uint32_t format_version() const noexcept override {
        return 1;
    }

    kephir2::BackendEncodeResult encode(
        const kephir2::ByteSource& input,
        const kephir2::BackendOptions&) override {

        kephir2::BackendEncodeResult out;
        out.blob.resize(static_cast<std::size_t>(input.size()));

        std::uint64_t offset = 0;
        while (offset < input.size()) {
            const auto remaining =
                static_cast<std::size_t>(input.size() - offset);
            const auto chunk = std::min<std::size_t>(4093, remaining);
            const auto got = input.read(
                offset,
                std::span<std::uint8_t>(
                    out.blob.data() + static_cast<std::size_t>(offset),
                    chunk));
            if (got == 0) {
                throw std::runtime_error("identity backend short source read");
            }
            offset += got;
        }

        out.stats.input_bytes = input.size();
        out.stats.output_bytes = out.blob.size();
        out.stats.workers_used = 1;
        return out;
    }

    kephir2::BackendStats decode(
        std::span<const std::uint8_t> blob,
        std::uint64_t expected_raw_bytes,
        kephir2::ByteSink& output,
        const kephir2::BackendOptions&) override {

        if (expected_raw_bytes != 0 && expected_raw_bytes != blob.size()) {
            throw std::runtime_error("identity backend raw length mismatch");
        }

        std::uint64_t offset = 0;
        while (offset < blob.size()) {
            const auto remaining =
                static_cast<std::size_t>(blob.size() - offset);
            const auto chunk = std::min<std::size_t>(17, remaining);
            output.write(
                offset,
                blob.subspan(static_cast<std::size_t>(offset), chunk));
            offset += chunk;
        }

        kephir2::BackendStats stats{};
        stats.input_bytes = blob.size();
        stats.output_bytes = blob.size();
        stats.workers_used = 1;
        return stats;
    }
};

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

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::vector<std::filesystem::path> files_under(const std::filesystem::path& root) {
    std::vector<std::filesystem::path> files;
    for (const auto& e : std::filesystem::recursive_directory_iterator(root)) {
        if (e.is_regular_file() && !e.is_symlink()) {
            files.push_back(e.path().lexically_relative(root));
        }
    }
    std::sort(files.begin(), files.end());
    return files;
}

} // namespace

int main() {
    using namespace kephir2;

    const auto base =
        std::filesystem::temp_directory_path() / "kephir2_execution_smoke";
    const auto input_dir = base / "input";
    const auto output_dir = base / "output";
    const auto file_out = base / "file_output";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(input_dir / "sub");

    write_repeat(
        input_dir / "a.dat",
        "int f(int x){return x*x+17;}\n",
        9000);
    write_repeat(
        input_dir / "sub" / "b.dat",
        "int g(int x){return x+31;}\n",
        7000);
    write_repeat(
        input_dir / "sub" / "prose.dat",
        "ordinary prose words and spaces form a sentence.\n",
        6000);

    {
        std::ofstream out(input_dir / "zero.dat", std::ios::binary);
        for (int i = 0; i < 5000; ++i) {
            const std::array<char,4> v{0,0,static_cast<char>(i & 0xff),0};
            out.write(v.data(), static_cast<std::streamsize>(v.size()));
        }
    }

    {
        std::ofstream empty(input_dir / "empty.dat", std::ios::binary);
    }

    IdentityBackend backend;
    ArchiveExecutor executor;

    const auto directory_archive =
        executor.compress_directory(input_dir, backend);

    const auto envelope = decode_kpf1_directory(directory_archive);
    assert(!envelope.manifest.empty());
    assert(envelope.group_names.size() == envelope.groups.size());

    executor.extract_directory(
        directory_archive,
        output_dir,
        backend);

    const auto input_files = files_under(input_dir);
    const auto output_files = files_under(output_dir);
    assert(input_files == output_files);

    for (const auto& rel : input_files) {
        assert(read_all(input_dir / rel) == read_all(output_dir / rel));
    }

    const auto single_file = input_dir / "a.dat";
    const auto file_archive =
        executor.compress_file(single_file, backend);

    const auto file_envelope = decode_kpf1_file(file_archive);
    assert(file_envelope.name == "a.dat");

    executor.extract_file(
        file_archive,
        file_out,
        backend);

    assert(
        read_all(single_file)
        == read_all(file_out / "a.dat"));

    std::filesystem::remove_all(base);
    return 0;
}
