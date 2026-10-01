#include "kephir2/aur2.hpp"
#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_seek.hpp"
#include "kephir2/native_k75.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        written += n;
    }
}

template <typename Fn>
bool throws(Fn&& fn) {
    try {
        fn();
        return false;
    } catch (const std::exception&) {
        return true;
    }
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto base = fs::temp_directory_path() / "kephir2_aur2_seek_smoke";
    const auto input = base / "sample.bin";
    const auto output = base / "out";
    fs::remove_all(base);
    fs::create_directories(base);

    write_repeat(
        input,
        "AUR2 seek index must be derived, optional and corruption checked.\n",
        192u * 1024u);

    NativeK75Backend backend;
    ArchiveExecutor executor;
    BackendOptions options;
    options.workers = 1;
    options.allow_local_experience = false;

    const auto legacy = executor.compress_file(input, backend, options);
    validate_seek_index(legacy); // legacy AUR2 without index remains valid

    const auto indexed = attach_seek_index(legacy);
    validate_seek_index(indexed);

    const auto model = decode_container(indexed);
    assert((model.header.feature_flags & feature_bit(Feature::SeekIndex)) != 0);
    assert(model.header.toc_offset == kFixedHeaderSize);
    assert(!model.sections.empty());
    assert(model.sections.front().type == static_cast<std::uint32_t>(SectionType::SeekIndex));

    const auto records = decode_seek_index(model.sections.front().payload);
    assert(records.size() + 1 == model.sections.size());
    assert(!records.empty());
    assert(records.front().section_offset > model.header.toc_offset);

    const auto refreshed = attach_seek_index(indexed);
    assert(refreshed == indexed);

    executor.extract_file(indexed, output, backend, options);
    assert(read_all(input) == read_all(output / input.filename()));

    auto corrupt = indexed;
    const std::size_t seek_payload =
        static_cast<std::size_t>(kFixedHeaderSize + kSectionHeaderSize);
    assert(corrupt.size() > seek_payload + 20);
    corrupt[seek_payload + 20] ^= 0x40u;
    assert(throws([&] { validate_seek_index(corrupt); }));

    fs::remove_all(base);
    return 0;
}
