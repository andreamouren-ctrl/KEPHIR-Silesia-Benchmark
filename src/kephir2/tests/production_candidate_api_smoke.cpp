#include "kephir2/execution.hpp"
#include "kephir2/kephir2_c.h"
#include "kephir2/native_k75.hpp"

#include <algorithm>
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
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    assert(out);

    std::size_t written = 0;
    while (written < size) {
        const auto n = std::min(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        written += n;
    }
    assert(out);
}

void write_all(
    const std::filesystem::path& path,
    const std::vector<std::uint8_t>& bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    assert(out);
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    assert(out);
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    assert(in);
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::string utf8(const std::filesystem::path& path) {
    const auto s = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(s.data()),
        s.size());
}

} // namespace

int main() {
    using namespace kephir2;
    constexpr std::size_t MiB = 1024u * 1024u;

    const auto base =
        std::filesystem::temp_directory_path()
        / "kephir2_exp117_api_candidate";
    const auto input = base / "candidate.txt";
    const auto adaptive_archive = base / "adaptive.kpf";
    const auto api_fast_archive = base / "api_fast.kpf";
    const auto api_auto_archive = base / "api_auto.kpf";
    const auto adaptive_extract = base / "adaptive_extract";
    const auto fast_extract = base / "fast_extract";
    const auto auto_extract = base / "auto_extract";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    write_repeat(
        input,
        "ordinary prose words and spaces form a natural sentence. "
        "long range context should remain stable across this stream.\n",
        10u * MiB);

    NativeK75Backend backend;
    ArchiveExecutor executor;

    BackendOptions baseline{};
    baseline.workers = 4;
    baseline.allow_local_experience = false;

    BackendOptions adaptive = baseline;
    adaptive.enable_adaptive_context = true;

    const auto direct_baseline =
        executor.compress_file(input, backend, baseline);
    const auto direct_adaptive =
        executor.compress_file(input, backend, adaptive);

    assert(!direct_baseline.empty());
    assert(!direct_adaptive.empty());
    assert(direct_adaptive != direct_baseline);
    assert(direct_adaptive.size() < direct_baseline.size());

    write_all(adaptive_archive, direct_adaptive);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    options.struct_size = sizeof(options);
    options.workers = 4;
    options.verify_integrity = 1;
    options.overwrite_output = 1;
    options.allow_local_experience = 0;

    const auto input_s = utf8(input);

    // FAST must remain byte-for-byte identical to the qualified baseline.
    options.profile = KEPHIR2_PROFILE_FAST;
    kephir2_result_v1 fast_result{};
    fast_result.struct_size = sizeof(fast_result);
    const auto api_fast_s = utf8(api_fast_archive);

    assert(kephir2_compress(
        engine,
        input_s.c_str(),
        api_fast_s.c_str(),
        &options,
        &fast_result) == KEPHIR2_OK);
    assert(fast_result.status == KEPHIR2_OK);
    assert(fast_result.input_bytes == std::filesystem::file_size(input));
    assert(fast_result.output_bytes == std::filesystem::file_size(api_fast_archive));
    assert(read_all(api_fast_archive) == direct_baseline);

    // EXP-117B contract: public AUTO must be exactly the adaptive core path.
    options.profile = KEPHIR2_PROFILE_AUTO;
    kephir2_result_v1 auto_result{};
    auto_result.struct_size = sizeof(auto_result);
    const auto api_auto_s = utf8(api_auto_archive);

    assert(kephir2_compress(
        engine,
        input_s.c_str(),
        api_auto_s.c_str(),
        &options,
        &auto_result) == KEPHIR2_OK);
    assert(auto_result.status == KEPHIR2_OK);
    assert(auto_result.input_bytes == std::filesystem::file_size(input));
    assert(auto_result.output_bytes == std::filesystem::file_size(api_auto_archive));
    assert(read_all(api_auto_archive) == direct_adaptive);
    assert(auto_result.output_bytes < fast_result.output_bytes);

    // Decoder compatibility is profile-independent: FAST must still decode an
    // adaptive archive produced by the core candidate.
    options.profile = KEPHIR2_PROFILE_FAST;
    kephir2_result_v1 adaptive_extract_result{};
    adaptive_extract_result.struct_size = sizeof(adaptive_extract_result);
    const auto adaptive_archive_s = utf8(adaptive_archive);
    const auto adaptive_extract_s = utf8(adaptive_extract);

    assert(kephir2_extract(
        engine,
        adaptive_archive_s.c_str(),
        adaptive_extract_s.c_str(),
        &options,
        &adaptive_extract_result) == KEPHIR2_OK);
    assert(adaptive_extract_result.status == KEPHIR2_OK);
    assert(read_all(input) == read_all(adaptive_extract / input.filename()));

    // FAST archive roundtrip.
    kephir2_result_v1 fast_extract_result{};
    fast_extract_result.struct_size = sizeof(fast_extract_result);
    const auto fast_extract_s = utf8(fast_extract);

    assert(kephir2_extract(
        engine,
        api_fast_s.c_str(),
        fast_extract_s.c_str(),
        &options,
        &fast_extract_result) == KEPHIR2_OK);
    assert(read_all(input) == read_all(fast_extract / input.filename()));

    // AUTO archive roundtrip through the public AUTO profile.
    options.profile = KEPHIR2_PROFILE_AUTO;
    kephir2_result_v1 auto_extract_result{};
    auto_extract_result.struct_size = sizeof(auto_extract_result);
    const auto auto_extract_s = utf8(auto_extract);

    assert(kephir2_extract(
        engine,
        api_auto_s.c_str(),
        auto_extract_s.c_str(),
        &options,
        &auto_extract_result) == KEPHIR2_OK);
    assert(auto_extract_result.status == KEPHIR2_OK);
    assert(read_all(input) == read_all(auto_extract / input.filename()));

    kephir2_destroy(engine);
    std::filesystem::remove_all(base);
    return 0;
}
