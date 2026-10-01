#include "kephir2/kephir2_c.h"

#include "kephir2/aur2_inspection.hpp"
#include "kephir2/native_k75.hpp"
#include "kephir2/operation.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

std::filesystem::path from_utf8(const char* value) {
    if (!value) return {};

    std::u8string text;
    while (*value != '\0') {
        text.push_back(static_cast<char8_t>(
            static_cast<unsigned char>(*value)));
        ++value;
    }
    return std::filesystem::path(text);
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to open AUR2 archive");
    }
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

bool valid_options(const kephir2_options_v1* options) noexcept {
    if (!options) return true;
    if (options->struct_size < sizeof(kephir2_options_v1)) return false;
    return options->profile >= KEPHIR2_PROFILE_AUTO
        && options->profile <= KEPHIR2_PROFILE_MAX;
}

void fill_result(
    kephir2_result_v1* result,
    kephir2_status status,
    std::string_view message,
    std::uint64_t input_bytes = 0,
    std::uint64_t output_bytes = 0,
    double elapsed_seconds = 0.0) noexcept {

    if (!result) return;
    std::memset(result, 0, sizeof(*result));
    result->struct_size = sizeof(*result);
    result->status = status;
    result->input_bytes = input_bytes;
    result->output_bytes = output_bytes;
    result->elapsed_seconds = elapsed_seconds;

    const auto n = std::min(message.size(), sizeof(result->message) - 1);
    if (n != 0) {
        std::memcpy(result->message, message.data(), n);
    }
    result->message[n] = '\0';
}

kephir2_status classify_error(std::string_view message) noexcept {
    if (message.find("cancel") != std::string_view::npos) {
        return KEPHIR2_CANCELLED;
    }
    if (message.find("CRC32 mismatch") != std::string_view::npos
        || message.find("integrity") != std::string_view::npos) {
        return KEPHIR2_INTEGRITY_ERROR;
    }
    if (message.find("not an AUR2") != std::string_view::npos
        || message.find("unsupported") != std::string_view::npos
        || message.find("version mismatch") != std::string_view::npos) {
        return KEPHIR2_UNSUPPORTED_ARCHIVE;
    }
    if (message.find("truncated") != std::string_view::npos
        || message.find("mismatch") != std::string_view::npos
        || message.find("duplicate") != std::string_view::npos
        || message.find("unsafe") != std::string_view::npos
        || message.find("unknown") != std::string_view::npos
        || message.find("gap") != std::string_view::npos
        || message.find("overlap") != std::string_view::npos
        || message.find("out of range") != std::string_view::npos
        || message.find("does not") != std::string_view::npos
        || message.find("requires") != std::string_view::npos) {
        return KEPHIR2_CORRUPT_ARCHIVE;
    }
    return KEPHIR2_IO_ERROR;
}

void emit_verify_progress(
    const kephir2_options_v1* options,
    double fraction,
    std::uint64_t processed,
    std::uint64_t total,
    const char* path_utf8) {

    if (!options || !options->progress_callback) return;

    kephir2_progress_v1 progress{};
    progress.struct_size = sizeof(progress);
    progress.phase = fraction >= 1.0
        ? KEPHIR2_PHASE_DONE
        : KEPHIR2_PHASE_VERIFYING;
    progress.fraction = std::clamp(fraction, 0.0, 1.0);
    progress.processed_bytes = processed;
    progress.total_bytes = total;
    progress.current_path_utf8 = path_utf8;
    options->progress_callback(&progress, options->user_data);
}

kephir2::OperationContext make_cancel_context(
    const kephir2_options_v1* options) {

    kephir2::OperationContext::CancelCallback cancel;
    if (options && options->cancel_callback) {
        cancel = [options]() {
            return options->cancel_callback(options->user_data) != 0;
        };
    }
    return kephir2::OperationContext({}, std::move(cancel));
}

kephir2::BackendOptions make_backend_options(
    const kephir2_options_v1* options,
    const kephir2::OperationContext* operation) {

    kephir2::BackendOptions out;
    out.operation = operation;
    if (options) {
        out.workers = options->workers;
        out.allow_local_experience = options->allow_local_experience != 0;
    }
    return out;
}

} // namespace

extern "C" {

void kephir2_options_init_v1(kephir2_options_v1* options) {
    if (!options) return;
    std::memset(options, 0, sizeof(*options));
    options->struct_size = sizeof(*options);
    options->profile = KEPHIR2_PROFILE_AUTO;
    options->workers = 0;
    options->verify_integrity = 1;
    options->overwrite_output = 0;
    options->allow_local_experience = 1;
}

kephir2_status kephir2_inspect(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_archive_info_v1* info) {

    if (!engine || !archive_utf8 || !info
        || info->struct_size < sizeof(kephir2_archive_info_v1)) {
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(path)) {
        return KEPHIR2_INPUT_NOT_FOUND;
    }

    try {
        const auto archive = read_all(path);
        const auto native = kephir2::aur2::inspect_archive(archive);

        std::memset(info, 0, sizeof(*info));
        info->struct_size = sizeof(*info);
        info->container_major = native.container_major;
        info->container_minor = native.container_minor;
        info->codec_major = native.codec_major;
        info->codec_minor = native.codec_minor;
        info->feature_flags = native.feature_flags;
        info->entry_count = native.entry_count;
        info->logical_bytes = native.logical_bytes;
        info->archive_bytes = native.archive_bytes;
        info->stream_count = native.stream_count;
        info->is_encrypted = native.is_encrypted ? 1 : 0;
        info->integrity_available = native.integrity_available ? 1 : 0;
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        return classify_error(error.what());
    } catch (...) {
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_list_entries(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_entry_callback callback,
    void* user_data) {

    if (!engine || !archive_utf8 || !callback) {
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(path)) {
        return KEPHIR2_INPUT_NOT_FOUND;
    }

    try {
        const auto archive = read_all(path);
        const auto entries = kephir2::aur2::list_entries(archive);

        for (const auto& native : entries) {
            kephir2_entry_info_v1 entry{};
            entry.struct_size = sizeof(entry);
            entry.entry_id = native.entry_id;
            entry.type = native.type == kephir2::aur2::EntryType::Directory
                ? KEPHIR2_ENTRY_DIRECTORY
                : KEPHIR2_ENTRY_FILE;
            entry.logical_size = native.logical_size;
            entry.stream_id = native.stream_id;
            entry.stream_offset = native.stream_offset;
            entry.attributes = native.attributes;
            entry.mtime_unix_ns = native.mtime_unix_ns;
            entry.path_utf8 = native.path.c_str();

            // Non-zero means the host has enough entries; stopping enumeration
            // is a successful operation rather than an engine cancellation.
            if (callback(&entry, user_data) != 0) {
                break;
            }
        }
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        return classify_error(error.what());
    } catch (...) {
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_test_archive(
    kephir2_engine* engine,
    const char* archive_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    const auto start = Clock::now();

    if (!engine || !archive_utf8 || !valid_options(options)) {
        fill_result(
            result,
            KEPHIR2_INVALID_ARGUMENT,
            "invalid AUR2 test arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(path)) {
        fill_result(
            result,
            KEPHIR2_INPUT_NOT_FOUND,
            "AUR2 archive not found");
        return KEPHIR2_INPUT_NOT_FOUND;
    }

    std::uint64_t input_bytes = 0;
    std::uint64_t logical_bytes = 0;

    try {
        const auto archive = read_all(path);
        input_bytes = archive.size();
        const auto info = kephir2::aur2::inspect_archive(archive);
        logical_bytes = info.logical_bytes;

        if (options && options->cancel_callback
            && options->cancel_callback(options->user_data) != 0) {
            throw kephir2::OperationCancelled{};
        }

        emit_verify_progress(
            options,
            0.0,
            0,
            logical_bytes,
            archive_utf8);

        auto operation = make_cancel_context(options);
        const auto backend_options = make_backend_options(options, &operation);
        kephir2::NativeK75Backend backend;
        kephir2::aur2::test_archive(
            archive,
            backend,
            backend_options);

        emit_verify_progress(
            options,
            1.0,
            logical_bytes,
            logical_bytes,
            archive_utf8);

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_OK,
            "AUR2 archive verification completed",
            input_bytes,
            logical_bytes,
            elapsed);
        return KEPHIR2_OK;
    } catch (const kephir2::OperationCancelled&) {
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_CANCELLED,
            "operation cancelled",
            input_bytes,
            logical_bytes,
            elapsed);
        return KEPHIR2_CANCELLED;
    } catch (const std::exception& error) {
        const auto status = classify_error(error.what());
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            status,
            error.what(),
            input_bytes,
            logical_bytes,
            elapsed);
        return status;
    } catch (...) {
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 verification error",
            input_bytes,
            logical_bytes,
            elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }
}

} // extern "C"
