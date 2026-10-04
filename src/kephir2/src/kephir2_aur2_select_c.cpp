#include "kephir2/kephir2_c.h"

#include "kephir2/aur2_inspection.hpp"
#include "kephir2/aur2_selection.hpp"
#include "kephir2/native_k75.hpp"
#include "kephir2/operation.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
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
    if (!in) throw std::runtime_error("unable to open AUR2 archive");
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
    if (n != 0) std::memcpy(result->message, message.data(), n);
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
    if (message.find("selected entry id") != std::string_view::npos) {
        return KEPHIR2_INVALID_ARGUMENT;
    }
    if (message.find("unsupported") != std::string_view::npos
        || message.find("version mismatch") != std::string_view::npos
        || message.find("not an AUR2") != std::string_view::npos) {
        return KEPHIR2_UNSUPPORTED_ARCHIVE;
    }
    if (message.find("truncated") != std::string_view::npos
        || message.find("mismatch") != std::string_view::npos
        || message.find("unsafe") != std::string_view::npos
        || message.find("overlap") != std::string_view::npos
        || message.find("out of range") != std::string_view::npos) {
        return KEPHIR2_CORRUPT_ARCHIVE;
    }
    return KEPHIR2_IO_ERROR;
}

kephir2::OperationContext make_operation(
    const kephir2_options_v1* options) {

    kephir2::OperationContext::ProgressCallback progress;
    if (options && options->progress_callback) {
        progress = [options](const kephir2::OperationProgress& native) {
            kephir2_progress_v1 out{};
            out.struct_size = sizeof(out);
            out.phase = KEPHIR2_PHASE_EXTRACTING;
            out.fraction = std::clamp(native.fraction, 0.0, 1.0);
            out.processed_bytes = native.processed_bytes;
            out.total_bytes = native.total_bytes;
            out.current_path_utf8 =
                native.current_path.empty() ? nullptr : native.current_path.c_str();
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

void emit_progress(
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
        : KEPHIR2_PHASE_EXTRACTING;
    progress.fraction = std::clamp(fraction, 0.0, 1.0);
    progress.processed_bytes = processed;
    progress.total_bytes = total;
    progress.current_path_utf8 = path_utf8;
    options->progress_callback(&progress, options->user_data);
}

} // namespace

extern "C" {

kephir2_status kephir2_extract_selected(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_selection_v1* selection,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    const auto start = Clock::now();

    if (!engine || !archive_utf8 || !output_directory_utf8 || !selection
        || selection->struct_size < sizeof(kephir2_selection_v1)
        || (selection->entry_count != 0 && !selection->entry_ids)
        || !valid_options(options)) {
        fill_result(result, KEPHIR2_INVALID_ARGUMENT, "invalid AUR2 selection arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto archive_path = from_utf8(archive_utf8);
    const auto output = from_utf8(output_directory_utf8);
    if (!std::filesystem::is_regular_file(archive_path)) {
        fill_result(result, KEPHIR2_INPUT_NOT_FOUND, "AUR2 archive not found");
        return KEPHIR2_INPUT_NOT_FOUND;
    }

    if (std::filesystem::exists(output)
        && options && !options->overwrite_output
        && !std::filesystem::is_empty(output)) {
        fill_result(result, KEPHIR2_OUTPUT_EXISTS, "output directory is not empty");
        return KEPHIR2_OUTPUT_EXISTS;
    }

    std::uint64_t input_bytes = 0;
    std::uint64_t output_bytes = 0;

    try {
        const auto archive = read_all(archive_path);
        input_bytes = archive.size();
        const auto entries = kephir2::aur2::list_entries(archive);

        std::unordered_map<std::uint64_t, std::uint64_t> sizes;
        sizes.reserve(entries.size());
        for (const auto& entry : entries) {
            sizes.emplace(
                entry.entry_id,
                entry.type == kephir2::aur2::EntryType::File
                    ? entry.logical_size
                    : 0);
        }

        std::vector<std::uint64_t> ids;
        ids.reserve(selection->entry_count);
        for (std::size_t i = 0; i < selection->entry_count; ++i) {
            const auto id = selection->entry_ids[i];
            const auto it = sizes.find(id);
            if (it == sizes.end()) {
                fill_result(result, KEPHIR2_INVALID_ARGUMENT, "selected entry id does not exist", input_bytes);
                return KEPHIR2_INVALID_ARGUMENT;
            }
            ids.push_back(id);
            if (it->second > UINT64_MAX - output_bytes) {
                throw std::runtime_error("selected output size overflow");
            }
            output_bytes += it->second;
        }

        emit_progress(options, 0.0, 0, output_bytes, archive_utf8);

        auto operation = make_operation(options);
        kephir2::BackendOptions backend_options;
        backend_options.operation = &operation;
        if (options) {
            backend_options.workers = options->workers;
            backend_options.allow_local_experience = options->allow_local_experience != 0;
        }

        kephir2::NativeK75Backend backend;
        kephir2::aur2::extract_selected(
            archive,
            output,
            backend,
            ids,
            backend_options);

        emit_progress(options, 1.0, output_bytes, output_bytes, output_directory_utf8);

        const auto elapsed = std::chrono::duration<double>(Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_OK,
            "selective extraction completed",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_OK;
    } catch (const kephir2::OperationCancelled&) {
        const auto elapsed = std::chrono::duration<double>(Clock::now() - start).count();
        fill_result(result, KEPHIR2_CANCELLED, "operation cancelled", input_bytes, output_bytes, elapsed);
        return KEPHIR2_CANCELLED;
    } catch (const std::exception& error) {
        const auto status = classify_error(error.what());
        const auto elapsed = std::chrono::duration<double>(Clock::now() - start).count();
        fill_result(result, status, error.what(), input_bytes, output_bytes, elapsed);
        return status;
    } catch (...) {
        const auto elapsed = std::chrono::duration<double>(Clock::now() - start).count();
        fill_result(result, KEPHIR2_INTERNAL_ERROR, "unknown selective extraction error", input_bytes, output_bytes, elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }
}

} // extern "C"
