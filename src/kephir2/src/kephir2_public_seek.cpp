#include "kephir2/kephir2_c.h"

#include "kephir2/aur2_file_extract.hpp"
#include "kephir2/aur2_indexed_file.hpp"
#include "kephir2/aur2_metadata.hpp"
#include "kephir2/aur2_seek.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <array>
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
kephir2_status kephir2_compress_metadata_payload(
    kephir2_engine*, const char*, const char*,
    const kephir2_options_v1*, kephir2_result_v1*);
kephir2_status kephir2_extract_metadata_payload(
    kephir2_engine*, const char*, const char*,
    const kephir2_options_v1*, kephir2_result_v1*);
kephir2_status kephir2_extract_selected_metadata_payload(
    kephir2_engine*, const char*, const char*,
    const kephir2_selection_v1*, const kephir2_options_v1*,
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
    if (!state.progress) return;
    if (progress->phase == KEPHIR2_PHASE_DONE) return;

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

bool options_value_valid(const kephir2_options_v1* options) noexcept {
    if (!options_shape_valid(options)) return false;
    if (!options) return true;
    return options->profile >= KEPHIR2_PROFILE_AUTO
        && options->profile <= KEPHIR2_PROFILE_MAX;
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
    const std::string text(value);
    std::u8string u8;
    u8.resize(text.size());
    std::transform(text.begin(), text.end(), u8.begin(), [](char c) {
        return static_cast<char8_t>(static_cast<unsigned char>(c));
    });
    return std::filesystem::path(u8);
}

std::string to_utf8(const std::filesystem::path& path) {
    const auto value = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(value.data()),
        value.size());
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unable to open AUR2 seek-index archive");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    std::span<const std::uint8_t> bytes) {

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("unable to rewrite AUR2 seek-index archive");
    if (!bytes.empty()) {
        out.write(
            reinterpret_cast<const char*>(bytes.data()),
            static_cast<std::streamsize>(bytes.size()));
    }
    out.flush();
    if (!out) throw std::runtime_error("unable to flush AUR2 seek-index archive");
}

std::filesystem::path staging_path(const std::filesystem::path& destination) {
    const auto ticks = static_cast<unsigned long long>(
        Clock::now().time_since_epoch().count());
    auto parent = destination.parent_path();
    if (parent.empty()) parent = ".";
    return parent / (
        destination.filename().string()
        + ".aur2-index-stage."
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
        throw std::runtime_error("unable to atomically publish indexed AUR2 archive");
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

bool has_aur2_magic_file(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    std::array<char, 4> magic{};
    in.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    return in.gcount() == static_cast<std::streamsize>(magic.size())
        && magic[0] == 'A'
        && magic[1] == 'U'
        && magic[2] == 'R'
        && magic[3] == '2';
}

kephir2_phase to_c_phase(kephir2::OperationPhase phase) noexcept {
    using P = kephir2::OperationPhase;
    switch (phase) {
    case P::Idle: return KEPHIR2_PHASE_IDLE;
    case P::Scanning: return KEPHIR2_PHASE_SCANNING;
    case P::Analyzing: return KEPHIR2_PHASE_ANALYZING;
    case P::Planning: return KEPHIR2_PHASE_PLANNING;
    case P::Packing: return KEPHIR2_PHASE_PACKING;
    case P::Compressing: return KEPHIR2_PHASE_COMPRESSING;
    case P::Writing: return KEPHIR2_PHASE_WRITING;
    case P::Verifying: return KEPHIR2_PHASE_VERIFYING;
    case P::Extracting: return KEPHIR2_PHASE_EXTRACTING;
    case P::Done: return KEPHIR2_PHASE_DONE;
    }
    return KEPHIR2_PHASE_IDLE;
}

kephir2::OperationContext make_file_backed_operation(
    const kephir2_options_v1* options) {

    kephir2::OperationContext::ProgressCallback progress;
    if (options && options->progress_callback) {
        progress = [options](const kephir2::OperationProgress& source) {
            kephir2_progress_v1 out{};
            out.struct_size = sizeof(out);
            out.phase = to_c_phase(source.phase);
            out.fraction = std::clamp(source.fraction, 0.0, 1.0);
            out.processed_bytes = source.processed_bytes;
            out.total_bytes = source.total_bytes;
            out.current_path_utf8 = source.current_path.empty()
                ? nullptr
                : source.current_path.c_str();
            options->progress_callback(&out, options->user_data);
        };
    }

    kephir2::OperationContext::CancelCallback cancel;
    if (options && options->cancel_callback) {
        cancel = [options]() {
            return options->cancel_callback(options->user_data) != 0;
        };
    }
    return kephir2::OperationContext(std::move(progress), std::move(cancel));
}

kephir2_status map_file_backed_error(
    const std::exception& error,
    kephir2_result_v1* result,
    std::uint64_t input_bytes,
    std::uint64_t output_bytes,
    double elapsed_seconds) noexcept {

    const std::string_view message(error.what());
    if (dynamic_cast<const kephir2::OperationCancelled*>(&error) != nullptr) {
        fill_result(
            result,
            KEPHIR2_CANCELLED,
            "operation cancelled",
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_CANCELLED;
    }
    if (message.find("CRC32") != std::string_view::npos
        || message.find("checksum") != std::string_view::npos) {
        fill_result(
            result,
            KEPHIR2_INTEGRITY_ERROR,
            message,
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_INTEGRITY_ERROR;
    }
    if (message.find("unsupported") != std::string_view::npos
        || message.find("backend format version") != std::string_view::npos) {
        fill_result(
            result,
            KEPHIR2_UNSUPPORTED_ARCHIVE,
            message,
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_UNSUPPORTED_ARCHIVE;
    }
    if (message.find("truncated") != std::string_view::npos
        || message.find("mismatch") != std::string_view::npos
        || message.find("seek-index") != std::string_view::npos
        || message.find("SEEK_INDEX") != std::string_view::npos
        || message.find("duplicate") != std::string_view::npos
        || message.find("missing required") != std::string_view::npos
        || message.find("unsafe AUR2") != std::string_view::npos
        || message.find("exceeds archive") != std::string_view::npos) {
        fill_result(
            result,
            KEPHIR2_CORRUPT_ARCHIVE,
            message,
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_CORRUPT_ARCHIVE;
    }

    fill_result(
        result,
        KEPHIR2_IO_ERROR,
        message,
        input_bytes,
        output_bytes,
        elapsed_seconds);
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
        return kephir2_compress_metadata_payload(
            engine, input_utf8, output_utf8, options, result);
    }

    const auto start = Clock::now();
    const auto destination = from_utf8(output_utf8);
    const bool overwrite = options ? options->overwrite_output != 0 : false;

    if (!overwrite && std::filesystem::exists(destination)) {
        return kephir2_compress_metadata_payload(
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

    const auto status = kephir2_compress_metadata_payload(
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
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_CANCELLED,
            "operation cancelled",
            inner_result.input_bytes,
            0,
            elapsed);
        return KEPHIR2_CANCELLED;
    }

    try {
        const auto archive = read_all(stage);
        const auto indexed = kephir2::aur2::attach_seek_index(archive);
        write_all(stage, indexed);

        if (cancelled(forwarder)) {
            remove_noexcept(stage);
            const auto elapsed = std::chrono::duration<double>(
                Clock::now() - start).count();
            fill_result(
                result,
                KEPHIR2_CANCELLED,
                "operation cancelled",
                inner_result.input_bytes,
                0,
                elapsed);
            return KEPHIR2_CANCELLED;
        }

        publish_stage(stage, destination, overwrite);
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        const auto output_bytes = std::filesystem::file_size(destination);

        fill_result(
            result,
            KEPHIR2_OK,
            "AUR2 compression completed with filesystem metadata and seek index",
            inner_result.input_bytes,
            output_bytes,
            elapsed);
        emit_done(
            forwarder,
            inner_result.input_bytes,
            inner_result.input_bytes);
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        remove_noexcept(stage);
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_IO_ERROR,
            error.what(),
            inner_result.input_bytes,
            0,
            elapsed);
        return KEPHIR2_IO_ERROR;
    } catch (...) {
        remove_noexcept(stage);
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 seek-index compression error",
            inner_result.input_bytes,
            0,
            elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !archive_utf8 || !output_directory_utf8
        || !options_value_valid(options)) {
        return kephir2_extract_metadata_payload(
            engine,
            archive_utf8,
            output_directory_utf8,
            options,
            result);
    }

    const auto archive_path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(archive_path)
        || !has_aur2_magic_file(archive_path)) {
        return kephir2_extract_metadata_payload(
            engine,
            archive_utf8,
            output_directory_utf8,
            options,
            result);
    }

    try {
        if (!kephir2::aur2::has_seek_index_file(archive_path)) {
            return kephir2_extract_metadata_payload(
                engine,
                archive_utf8,
                output_directory_utf8,
                options,
                result);
        }
    } catch (const std::exception& error) {
        std::error_code ec;
        auto bytes = std::filesystem::file_size(archive_path, ec);
        if (ec) bytes = 0;
        return map_file_backed_error(
            error,
            result,
            bytes,
            0,
            0.0);
    }

    const auto start = Clock::now();
    const auto output = from_utf8(output_directory_utf8);
    std::uint64_t input_bytes = 0;
    std::uint64_t output_bytes = 0;

    try {
        input_bytes = std::filesystem::file_size(archive_path);
        const bool overwrite = options ? options->overwrite_output != 0 : false;
        if (std::filesystem::exists(output)
            && !overwrite
            && !std::filesystem::is_empty(output)) {
            fill_result(
                result,
                KEPHIR2_OUTPUT_EXISTS,
                "output directory is not empty",
                input_bytes,
                0,
                std::chrono::duration<double>(Clock::now() - start).count());
            return KEPHIR2_OUTPUT_EXISTS;
        }

        const auto info = kephir2::aur2::inspect_indexed_file(archive_path);
        output_bytes = info.logical_bytes;

        auto operation = make_file_backed_operation(options);
        kephir2::BackendOptions backend_options;
        backend_options.workers = options ? options->workers : 0;
        backend_options.allow_local_experience =
            !options || options->allow_local_experience != 0;
        backend_options.operation = &operation;

        operation.report({
            kephir2::OperationPhase::Extracting,
            0.0,
            0,
            output_bytes,
            archive_path.generic_string()
        });

        kephir2::NativeK75Backend backend;
        kephir2::aur2::extract_indexed_file_backed(
            archive_path,
            output,
            backend,
            backend_options);

        operation.throw_if_cancelled();
        kephir2::aur2::restore_filesystem_metadata_file(
            archive_path,
            output);
        operation.throw_if_cancelled();

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        if (options && options->progress_callback) {
            kephir2_progress_v1 done{};
            done.struct_size = sizeof(done);
            done.phase = KEPHIR2_PHASE_DONE;
            done.fraction = 1.0;
            done.processed_bytes = output_bytes;
            done.total_bytes = output_bytes;
            done.current_path_utf8 = output_directory_utf8;
            options->progress_callback(&done, options->user_data);
        }

        fill_result(
            result,
            KEPHIR2_OK,
            "AUR2 indexed file-backed extraction completed with filesystem metadata",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        return map_file_backed_error(
            error,
            result,
            input_bytes,
            output_bytes,
            std::chrono::duration<double>(Clock::now() - start).count());
    } catch (...) {
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 file-backed extraction error",
            input_bytes,
            output_bytes,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_extract_selected(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_selection_v1* selection,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    return kephir2_extract_selected_metadata_payload(
        engine,
        archive_utf8,
        output_directory_utf8,
        selection,
        options,
        result);
}

} // extern "C"
