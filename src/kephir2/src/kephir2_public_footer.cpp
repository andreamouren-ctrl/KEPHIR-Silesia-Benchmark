#include "kephir2/kephir2_c.h"

#include "kephir2/aur2_footer.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <span>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

extern "C" {
kephir2_status kephir2_compress_seek_payload(
    kephir2_engine*, const char*, const char*,
    const kephir2_options_v1*, kephir2_result_v1*);
kephir2_status kephir2_test_archive_indexed(
    kephir2_engine*, const char*, const kephir2_options_v1*,
    kephir2_result_v1*);
}

namespace {

using Clock = std::chrono::steady_clock;

struct CallbackForwarder {
    kephir2_progress_callback progress{nullptr};
    kephir2_cancel_callback cancel{nullptr};
    void* original_user_data{nullptr};
    std::string final_path;
};

void forward_progress(const kephir2_progress_v1* progress, void* user_data) {
    if (!progress || !user_data) return;
    auto& state = *static_cast<CallbackForwarder*>(user_data);
    if (!state.progress || progress->phase == KEPHIR2_PHASE_DONE) return;
    auto forwarded = *progress;
    if (progress->phase == KEPHIR2_PHASE_WRITING && !state.final_path.empty()) {
        forwarded.current_path_utf8 = state.final_path.c_str();
    }
    state.progress(&forwarded, state.original_user_data);
}

int forward_cancel(void* user_data) {
    if (!user_data) return 0;
    const auto& state = *static_cast<const CallbackForwarder*>(user_data);
    return state.cancel ? state.cancel(state.original_user_data) : 0;
}

bool cancelled(const CallbackForwarder& state) noexcept {
    return state.cancel && state.cancel(state.original_user_data) != 0;
}

void emit_done(
    const CallbackForwarder& state,
    std::uint64_t processed,
    std::uint64_t total) {

    if (!state.progress) return;
    kephir2_progress_v1 progress{};
    progress.struct_size = sizeof(progress);
    progress.phase = KEPHIR2_PHASE_DONE;
    progress.fraction = 1.0;
    progress.processed_bytes = processed;
    progress.total_bytes = total;
    progress.current_path_utf8 = state.final_path.empty()
        ? nullptr
        : state.final_path.c_str();
    state.progress(&progress, state.original_user_data);
}

void fill_result(
    kephir2_result_v1* result,
    kephir2_status status,
    std::string_view message,
    std::uint64_t input_bytes,
    std::uint64_t output_bytes,
    double elapsed_seconds) noexcept {

    if (!result) return;
    std::memset(result, 0, sizeof(*result));
    result->struct_size = sizeof(*result);
    result->status = status;
    result->input_bytes = input_bytes;
    result->output_bytes = output_bytes;
    result->elapsed_seconds = elapsed_seconds;
    const auto n = (std::min)(message.size(), sizeof(result->message) - 1);
    if (n) std::memcpy(result->message, message.data(), n);
    result->message[n] = '\0';
}

bool options_shape_valid(const kephir2_options_v1* options) noexcept {
    return !options || options->struct_size >= sizeof(kephir2_options_v1);
}

kephir2_options_v1 forwarded_options(
    const kephir2_options_v1* source,
    CallbackForwarder& forwarder) {

    kephir2_options_v1 out{};
    if (source && source->struct_size >= sizeof(kephir2_options_v1)) {
        out = *source;
    } else {
        kephir2_options_init_v1(&out);
    }
    out.struct_size = sizeof(out);
    forwarder.progress = out.progress_callback;
    forwarder.cancel = out.cancel_callback;
    forwarder.original_user_data = out.user_data;
    out.progress_callback = forwarder.progress ? forward_progress : nullptr;
    out.cancel_callback = forwarder.cancel ? forward_cancel : nullptr;
    out.user_data = &forwarder;
    return out;
}

std::filesystem::path from_utf8(const char* value) {
    if (!value) return {};
    std::u8string text;
    while (*value != '\0') {
        text.push_back(static_cast<char8_t>(static_cast<unsigned char>(*value)));
        ++value;
    }
    return std::filesystem::path(text);
}

std::string to_utf8(const std::filesystem::path& path) {
    const auto value = path.generic_u8string();
    return std::string(reinterpret_cast<const char*>(value.data()), value.size());
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unable to open AUR2 footer archive");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    std::span<const std::uint8_t> bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("unable to rewrite AUR2 footer archive");
    if (!bytes.empty()) {
        out.write(
            reinterpret_cast<const char*>(bytes.data()),
            static_cast<std::streamsize>(bytes.size()));
    }
    out.flush();
    if (!out) throw std::runtime_error("unable to flush AUR2 footer archive");
}

std::filesystem::path staging_path(const std::filesystem::path& destination) {
    const auto ticks = static_cast<unsigned long long>(
        Clock::now().time_since_epoch().count());
    auto parent = destination.parent_path();
    if (parent.empty()) parent = ".";
    return parent / (
        destination.filename().string()
        + ".aur2-footer-stage."
        + std::to_string(ticks));
}

void publish_stage(
    const std::filesystem::path& stage,
    const std::filesystem::path& destination,
    bool overwrite) {

    if (!overwrite && std::filesystem::exists(destination)) {
        throw std::runtime_error("output already exists");
    }
#ifdef _WIN32
    const DWORD flags = overwrite
        ? (MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)
        : MOVEFILE_WRITE_THROUGH;
    if (!MoveFileExW(stage.c_str(), destination.c_str(), flags)) {
        throw std::runtime_error("unable to atomically publish footer AUR2 archive");
    }
#else
    std::filesystem::rename(stage, destination);
#endif
}

void remove_noexcept(const std::filesystem::path& path) noexcept {
    if (path.empty()) return;
    std::error_code ec;
    std::filesystem::remove(path, ec);
}

bool has_aur2_magic(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= 4
        && bytes[0] == 'A'
        && bytes[1] == 'U'
        && bytes[2] == 'R'
        && bytes[3] == '2';
}

kephir2_status footer_error_status(std::string_view message) noexcept {
    if (message.find("CRC32") != std::string_view::npos
        || message.find("checksum") != std::string_view::npos) {
        return KEPHIR2_INTEGRITY_ERROR;
    }
    if (message.find("footer") != std::string_view::npos
        || message.find("FTR1") != std::string_view::npos
        || message.find("SEEK_INDEX") != std::string_view::npos
        || message.find("seek-index") != std::string_view::npos
        || message.find("truncated") != std::string_view::npos
        || message.find("mismatch") != std::string_view::npos) {
        return KEPHIR2_CORRUPT_ARCHIVE;
    }
    return KEPHIR2_IO_ERROR;
}

} // namespace

extern "C" {

kephir2_status kephir2_compress(
    kephir2_engine* engine,
    const char* input_utf8,
    const char* output_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !input_utf8 || !output_utf8 || !options_shape_valid(options)) {
        return kephir2_compress_seek_payload(
            engine, input_utf8, output_utf8, options, result);
    }

    const auto start = Clock::now();
    const auto destination = from_utf8(output_utf8);
    const bool overwrite = options ? options->overwrite_output != 0 : false;

    if (!overwrite && std::filesystem::exists(destination)) {
        return kephir2_compress_seek_payload(
            engine, input_utf8, output_utf8, options, result);
    }

    const auto stage = staging_path(destination);
    const auto stage_utf8 = to_utf8(stage);

    CallbackForwarder forwarder;
    forwarder.final_path = to_utf8(destination);
    auto inner_options = forwarded_options(options, forwarder);
    inner_options.overwrite_output = 1;

    kephir2_result_v1 inner_result{};
    inner_result.struct_size = sizeof(inner_result);
    const auto status = kephir2_compress_seek_payload(
        engine,
        input_utf8,
        stage_utf8.c_str(),
        &inner_options,
        &inner_result);

    if (status != KEPHIR2_OK) {
        remove_noexcept(stage);
        if (result) *result = inner_result;
        return status;
    }
    if (cancelled(forwarder)) {
        remove_noexcept(stage);
        fill_result(
            result,
            KEPHIR2_CANCELLED,
            "operation cancelled",
            inner_result.input_bytes,
            0,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_CANCELLED;
    }

    try {
        const auto archive = read_all(stage);
        const auto finished = kephir2::aur2::attach_footer_integrity(archive);
        write_all(stage, finished);

        if (cancelled(forwarder)) {
            remove_noexcept(stage);
            fill_result(
                result,
                KEPHIR2_CANCELLED,
                "operation cancelled",
                inner_result.input_bytes,
                0,
                std::chrono::duration<double>(Clock::now() - start).count());
            return KEPHIR2_CANCELLED;
        }

        publish_stage(stage, destination, overwrite);
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        const auto output_bytes = std::filesystem::file_size(destination);
        fill_result(
            result,
            KEPHIR2_OK,
            "AUR2 compression completed with metadata, seek index and footer integrity",
            inner_result.input_bytes,
            output_bytes,
            elapsed);
        emit_done(forwarder, inner_result.input_bytes, inner_result.input_bytes);
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        remove_noexcept(stage);
        fill_result(
            result,
            KEPHIR2_IO_ERROR,
            error.what(),
            inner_result.input_bytes,
            0,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_IO_ERROR;
    } catch (...) {
        remove_noexcept(stage);
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 footer compression error",
            inner_result.input_bytes,
            0,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_test_archive(
    kephir2_engine* engine,
    const char* archive_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !archive_utf8) {
        return kephir2_test_archive_indexed(
            engine, archive_utf8, options, result);
    }

    const auto path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(path)) {
        return kephir2_test_archive_indexed(
            engine, archive_utf8, options, result);
    }

    const auto start = Clock::now();
    try {
        const auto archive = read_all(path);
        if (has_aur2_magic(archive)) {
            kephir2::aur2::validate_footer_integrity(archive);
        }
    } catch (const std::exception& error) {
        const auto status = footer_error_status(error.what());
        std::error_code ec;
        auto bytes = std::filesystem::file_size(path, ec);
        if (ec) bytes = 0;
        fill_result(
            result,
            status,
            error.what(),
            bytes,
            0,
            std::chrono::duration<double>(Clock::now() - start).count());
        return status;
    } catch (...) {
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 footer validation error",
            0,
            0,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_INTERNAL_ERROR;
    }

    return kephir2_test_archive_indexed(
        engine, archive_utf8, options, result);
}

} // extern "C"
