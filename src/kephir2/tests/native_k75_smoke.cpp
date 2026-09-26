#include "kephir2/archive.hpp"
#include "kephir2/execution.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

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

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::vector<std::filesystem::path> list_files(
    const std::filesystem::path& root) {

    std::vector<std::filesystem::path> out;
    for (const auto& e : std::filesystem::recursive_directory_iterator(root)) {
        if (e.is_regular_file() && !e.is_symlink()) {
            out.push_back(e.path().lexically_relative(root));
        }
    }
    std::sort(out.begin(), out.end());
    return out;
}

} // namespace

int main() {
    using namespace kephir2;

    const auto base =
        std::filesystem::temp_directory_path() / "kephir2_native_k75_smoke";
    const auto input = base / "input";
    const auto restored = base / "restored";
    const auto single_out = base / "single";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(input / "sub");

    write_repeat(
        input / "code.dat",
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n",
        128u * 1024u);

    write_repeat(
        input / "sub" / "prose.dat",
        "ordinary prose words and spaces form a natural sentence. ",
        192u * 1024u);

    {
        std::ofstream out(input / "sub" / "binary.dat", std::ios::binary);
        for (int i = 0; i < 256 * 1024; ++i) {
            const std::array<char,4> v{
                0,
                static_cast<char>(i & 0xff),
                0,
                static_cast<char>((i >> 3) & 0xff)
            };
            out.write(v.data(), static_cast<std::streamsize>(v.size()));
        }
    }

    NativeK75Backend backend;
    ArchiveExecutor executor;

    const auto dir_archive =
        executor.compress_directory(input, backend);

    assert(dir_archive.size() > 5);
    assert(dir_archive[0] == 'K');
    assert(dir_archive[1] == 'P');
    assert(dir_archive[2] == 'F');
    assert(dir_archive[3] == '1');

    executor.extract_directory(
        dir_archive,
        restored,
        backend);

    const auto before = list_files(input);
    const auto after = list_files(restored);
    assert(before == after);

    for (const auto& rel : before) {
        assert(read_all(input / rel) == read_all(restored / rel));
    }

    const auto single = input / "code.dat";
    const auto file_archive =
        executor.compress_file(single, backend);

    executor.extract_file(
        file_archive,
        single_out,
        backend);

    assert(
        read_all(single)
        == read_all(single_out / "code.dat"));

    std::filesystem::remove_all(base);
    return 0;
}
