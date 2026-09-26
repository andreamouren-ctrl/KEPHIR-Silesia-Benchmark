#include "kephir2/kephir2_c.h"

#include <algorithm>
#include <cassert>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

struct CallbackState {
    int progress_calls{0};
    kephir2_phase last_phase{KEPHIR2_PHASE_IDLE};
    bool cancel{false};
};

void on_progress(
    const kephir2_progress_v1* progress,
    void* user_data) {

    auto* state = static_cast<CallbackState*>(user_data);
    assert(progress != nullptr);
    assert(progress->struct_size == sizeof(kephir2_progress_v1));
    assert(progress->fraction >= 0.0);
    assert(progress->fraction <= 1.0);
    ++state->progress_calls;
    state->last_phase = progress->phase;
}

int should_cancel(void* user_data) {
    const auto* state = static_cast<CallbackState*>(user_data);
    return state->cancel ? 1 : 0;
}

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

std::string utf8(const std::filesystem::path& path) {
    const auto s = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(s.data()),
        s.size());
}

} // namespace

int main() {
    assert(kephir2_api_version() == KEPHIR2_API_VERSION);
    assert(std::strcmp(kephir2_engine_version(), "2.0-dev-native") == 0);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    const auto base =
        std::filesystem::temp_directory_path() / "kephir2_api_smoke";
    const auto input = base / "input.dat";
    const auto archive = base / "input.kpf";
    const auto extracted = base / "extracted";
    const auto cancelled_archive = base / "cancelled.kpf";
    const auto directory = base / "dir_input";
    const auto dir_archive = base / "dir.kpf";
    const auto dir_out = base / "dir_out";

    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    write_repeat(
        input,
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n",
        192u * 1024u);

    CallbackState callbacks{};

    kephir2_options_v1 options{};
    options.struct_size = sizeof(options);
    options.profile = KEPHIR2_PROFILE_AUTO;
    options.workers = 1;
    options.verify_integrity = 1;
    options.overwrite_output = 1;
    options.allow_local_experience = 0;
    options.progress_callback = on_progress;
    options.cancel_callback = should_cancel;
    options.user_data = &callbacks;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);

    const auto input_s = utf8(input);
    const auto archive_s = utf8(archive);

    const auto c = kephir2_compress(
        engine,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &result);

    assert(c == KEPHIR2_OK);
    assert(result.status == KEPHIR2_OK);
    assert(result.input_bytes == std::filesystem::file_size(input));
    assert(result.output_bytes == std::filesystem::file_size(archive));
    assert(callbacks.progress_calls > 0);
    assert(callbacks.last_phase == KEPHIR2_PHASE_DONE);

    callbacks.progress_calls = 0;
    callbacks.last_phase = KEPHIR2_PHASE_IDLE;

    kephir2_result_v1 extract_result{};
    extract_result.struct_size = sizeof(extract_result);
    const auto extracted_s = utf8(extracted);

    const auto x = kephir2_extract(
        engine,
        archive_s.c_str(),
        extracted_s.c_str(),
        &options,
        &extract_result);

    assert(x == KEPHIR2_OK);
    assert(extract_result.status == KEPHIR2_OK);
    assert(
        read_all(input)
        == read_all(extracted / input.filename()));
    assert(callbacks.last_phase == KEPHIR2_PHASE_DONE);

    write_repeat(
        directory / "code0.dat",
        "int f(int x){return x*x+17;}\n",
        96u * 1024u);
    write_repeat(
        directory / "sub" / "prose.dat",
        "ordinary prose words and spaces form a natural sentence. ",
        96u * 1024u);

    kephir2_result_v1 dir_result{};
    dir_result.struct_size = sizeof(dir_result);
    const auto directory_s = utf8(directory);
    const auto dir_archive_s = utf8(dir_archive);

    assert(kephir2_compress(
        engine,
        directory_s.c_str(),
        dir_archive_s.c_str(),
        &options,
        &dir_result) == KEPHIR2_OK);

    const auto dir_out_s = utf8(dir_out);
    kephir2_result_v1 dir_extract_result{};
    dir_extract_result.struct_size = sizeof(dir_extract_result);

    assert(kephir2_extract(
        engine,
        dir_archive_s.c_str(),
        dir_out_s.c_str(),
        &options,
        &dir_extract_result) == KEPHIR2_OK);

    assert(
        read_all(directory / "code0.dat")
        == read_all(dir_out / "code0.dat"));
    assert(
        read_all(directory / "sub" / "prose.dat")
        == read_all(dir_out / "sub" / "prose.dat"));

    callbacks.cancel = true;
    kephir2_result_v1 cancelled{};
    cancelled.struct_size = sizeof(cancelled);
    const auto cancelled_s = utf8(cancelled_archive);

    assert(kephir2_compress(
        engine,
        input_s.c_str(),
        cancelled_s.c_str(),
        &options,
        &cancelled) == KEPHIR2_CANCELLED);
    assert(!std::filesystem::exists(cancelled_archive));

    kephir2_result_v1 invalid{};
    invalid.struct_size = sizeof(invalid);
    assert(kephir2_compress(
        nullptr,
        input_s.c_str(),
        archive_s.c_str(),
        &options,
        &invalid) == KEPHIR2_INVALID_ARGUMENT);

    kephir2_destroy(engine);
    std::filesystem::remove_all(base);
    return 0;
}
