#include "kephir2/aur2_execution.hpp"
#include "kephir2/aur2_finalize_file.hpp"
#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/kephir2_c.h"
#include "kephir2/native_k75.hpp"
#include "kephir2/strategy.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Sample {
    kephir2_phase phase{KEPHIR2_PHASE_IDLE};
    double fraction{0.0};
    std::uint64_t processed{0};
    std::uint64_t total{0};
};

struct Trace {
    std::vector<Sample> samples;
};

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::string utf8(const std::filesystem::path& path) {
    const auto text = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(text.data()),
        text.size());
}

void progress_callback(const kephir2_progress_v1* progress, void* user_data) {
    if (!progress || !user_data) return;
    auto& trace = *static_cast<Trace*>(user_data);
    trace.samples.push_back({
        progress->phase,
        progress->fraction,
        progress->processed_bytes,
        progress->total_bytes
    });
}

void write_repeat(
    const std::filesystem::path& path,
    const std::string& pattern,
    std::size_t size) {

    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create progress fixture");
    std::size_t written = 0;
    while (written < size) {
        const auto n = (std::min)(pattern.size(), size - written);
        out.write(pattern.data(), static_cast<std::streamsize>(n));
        require(static_cast<bool>(out), "unable to write progress fixture");
        written += n;
    }
}

void write_binary(const std::filesystem::path& path, std::size_t size) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to create binary progress fixture");
    std::uint32_t state = 0x12345678u;
    for (std::size_t i = 0; i < size; ++i) {
        state = state * 1664525u + 1013904223u;
        const auto byte = static_cast<char>((state >> 24u) & 0xffu);
        out.write(&byte, 1);
    }
    require(static_cast<bool>(out), "unable to persist binary progress fixture");
}

void write_bytes(const std::filesystem::path& path, const std::vector<std::uint8_t>& bytes) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    require(static_cast<bool>(out), "unable to write base progress archive");
    out.write(
        reinterpret_cast<const char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size()));
    require(static_cast<bool>(out), "unable to persist base progress archive");
}

void validate_trace(
    const Trace& trace,
    std::uint64_t expected_total,
    const std::string& label) {

    double last_fraction = 0.0;
    std::uint64_t last_processed = 0;
    bool saw_midpoint = false;
    std::size_t done_count = 0;

    for (const auto& sample : trace.samples) {
        require(sample.fraction >= -1e-12 && sample.fraction <= 1.0 + 1e-12,
                label + ": fraction outside [0,1]");

        if (sample.phase == KEPHIR2_PHASE_EXTRACTING) {
            require(sample.fraction + 1e-12 >= last_fraction,
                    label + ": extraction fraction regressed");
            require(sample.processed >= last_processed,
                    label + ": processed bytes regressed");
            require(sample.total == expected_total,
                    label + ": extraction total changed");
            if (sample.fraction > 0.0 && sample.fraction < 1.0) {
                saw_midpoint = true;
            }
            last_fraction = sample.fraction;
            last_processed = sample.processed;
        } else if (sample.phase == KEPHIR2_PHASE_DONE) {
            ++done_count;
            require(std::abs(sample.fraction - 1.0) < 1e-12,
                    label + ": DONE fraction is not 1");
            require(sample.processed == expected_total,
                    label + ": DONE processed mismatch");
            require(sample.total == expected_total,
                    label + ": DONE total mismatch");
        }
    }

    require(saw_midpoint, label + ": no intermediate progress sample observed");
    require(done_count == 1, label + ": DONE callback count mismatch");
}

} // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace kephir2;
    using namespace kephir2::aur2;

    const auto root = fs::temp_directory_path() / "kephir2_aur2_progress_smoke";
    const auto input = root / "input";
    const auto base_archive = root / "base.aur";
    const auto archive = root / "final.aur";
    const auto full_output = root / "full";
    const auto selected_output = root / "selected";

    fs::remove_all(root);
    fs::create_directories(input / "empty-dir");

    write_repeat(
        input / "code.cpp",
        "template<class T> T combine(T a,T b){ return a + b; }\n",
        768u * 1024u);
    write_repeat(
        input / "prose.txt",
        "The quiet archive contains ordinary words, spaces and sentences. ",
        704u * 1024u);
    write_binary(input / "random.bin", 640u * 1024u);
    write_repeat(
        input / "zeros.bin",
        std::string("\0\0\0\0\1\0\0\0", 8),
        576u * 1024u);

    NativeK75Backend backend;
    BackendOptions backend_options;
    backend_options.workers = 2;
    backend_options.allow_local_experience = false;

    ArchiveExecutor executor;
    const auto base_bytes = executor.compress_directory(
        input,
        backend,
        backend_options,
        Layout::Smart);
    write_bytes(base_archive, base_bytes);
    finalize_archive_file_backed(base_archive, input, archive);

    const auto info = inspect_indexed_file(archive);
    require(info.stream_count >= 2,
            "progress fixture did not create multiple SMART streams");

    auto* engine = kephir2_create();
    require(engine != nullptr, "kephir2_create returned null");

    kephir2_options_v1 options{};
    kephir2_options_init_v1(&options);
    options.workers = 2;
    options.overwrite_output = 1;
    options.allow_local_experience = 0;
    options.verify_integrity = 1;
    options.progress_callback = progress_callback;

    const auto archive_s = utf8(archive);
    const auto full_output_s = utf8(full_output);
    Trace full_trace;
    options.user_data = &full_trace;
    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);
    require(kephir2_extract(
        engine,
        archive_s.c_str(),
        full_output_s.c_str(),
        &options,
        &result) == KEPHIR2_OK,
        std::string("full progress extraction failed: ") + result.message);
    validate_trace(full_trace, info.logical_bytes, "full");

    const auto entries = list_indexed_file(archive);
    std::map<std::uint64_t, const FileEntry*> first_by_stream;
    for (const auto& entry : entries) {
        if (entry.type != EntryType::File || entry.stream_id == 0 || entry.logical_size == 0) {
            continue;
        }
        first_by_stream.emplace(entry.stream_id, &entry);
    }
    require(first_by_stream.size() >= 2,
            "progress fixture lacks two selectable streams");

    std::vector<std::uint64_t> selected_ids;
    std::uint64_t selected_total = 0;
    for (const auto& [stream_id, entry] : first_by_stream) {
        (void)stream_id;
        selected_ids.push_back(entry->entry_id);
        selected_total += entry->logical_size;
        if (selected_ids.size() == 2) break;
    }

    kephir2_selection_v1 selection{};
    selection.struct_size = sizeof(selection);
    selection.entry_ids = selected_ids.data();
    selection.entry_count = selected_ids.size();

    const auto selected_output_s = utf8(selected_output);
    Trace selected_trace;
    options.user_data = &selected_trace;
    result = {};
    result.struct_size = sizeof(result);
    require(kephir2_extract_selected(
        engine,
        archive_s.c_str(),
        selected_output_s.c_str(),
        &selection,
        &options,
        &result) == KEPHIR2_OK,
        std::string("selective progress extraction failed: ") + result.message);
    validate_trace(selected_trace, selected_total, "selective");

    kephir2_destroy(engine);
    fs::remove_all(root);
    return 0;
}
