#include "kephir2/kephir2_c.h"

#include "kephir2/transactional_directory.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <string>
#include <string_view>

extern "C" {
kephir2_status kephir2_extract_indexed_payload(
    kephir2_engine*, const char*, const char*,
    const kephir2_options_v1*, kephir2_result_v1*);
kephir2_status kephir2_extract_selected_indexed_payload(
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
    const auto text = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(text.data()),
        text.size());
}

void forward_progress(const kephir2_progress_v1* progress, void* user_data) {
    if (!progress || !user_data) return;
    auto& state = *static_cast<CallbackForwarder*>(user_data);
    if (!state.progress || progress->phase == KEPHIR2_PHASE_DONE) return;
    state.progress(progress, state.original_user_data);
}

int forward_cancel(void* user_data) {
    if (!user_data) return 0;
    const auto& state = *static_cast<const CallbackForwarder*>(user_data);
    return state.cancel ? state.cancel(state.original_user_data) : 0;
}

bool cancelled(const CallbackForwarder& state) noexcept {
    return state.cancel && state.cancel(state.original_user_data) != 0;
}

kephir2_options_v1 forwarded_options(
    const kephir2_options_v1* source,
    CallbackForwarder& state) {

    kephir2_options_v1 out{};
    if (source && source->struct_size >= sizeof(kephir2_options_v1)) {
        out = *source;
    } else {
        kephir2_options_init_v1(&out);
    }
    out.struct_size = sizeof(out);

    state.progress = out.progress_callback;
    state.cancel = out.cancel_callback;
    state.original_user_data = out.user_data;

    out.progress_callback = state.progress ? forward_progress : nullptr;
    out.cancel_callback = state.cancel ? forward_cancel : nullptr;
    out.user_data = &state;
    out.overwrite_output = 1;
    return out;
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

template <typename Invoke>
kephir2_status run_transactional_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result,
    std::string_view success_message,
    Invoke&& invoke) {

    const auto start = Clock::now();
    const auto destination = from_utf8(output_directory_utf8);
    const bool overwrite = options ? options->overwrite_output != 0 : false;

    std::error_code exists_ec;
    const bool destination_exists = std::filesystem::exists(destination, exists_ec);
    if (exists_ec) {
        return invoke(output_directory_utf8, options, result);
    }

    if (destination_exists && !std::filesystem::is_directory(destination)) {
        return invoke(output_directory_utf8, options, result);
    }

    if (destination_exists && !overwrite) {
        std::error_code empty_ec;
        const bool empty = std::filesystem::is_empty(destination, empty_ec);
        if (empty_ec || !empty) {
            return invoke(output_directory_utf8, options, result);
        }
    }

    const auto stage = kephir2::make_directory_stage_path(
        destination,
        "aur2-extract-stage");
    const auto stage_utf8 = to_utf8(stage);

    CallbackForwarder forwarder;
    forwarder.final_path = to_utf8(destination);
    auto inner_options = forwarded_options(options, forwarder);

    kephir2_result_v1 inner_result{};
    inner_result.struct_size = sizeof(inner_result);

    try {
        kephir2::prepare_directory_stage(
            stage,
            destination,
            destination_exists);

        const auto status = invoke(
            stage_utf8.c_str(),
            &inner_options,
            &inner_result);

        if (status != KEPHIR2_OK) {
            kephir2::remove_directory_tree_noexcept(stage);
            if (result) *result = inner_result;
            return status;
        }

        if (cancelled(forwarder)) {
            kephir2::remove_directory_tree_noexcept(stage);
            fill_result(
                result,
                KEPHIR2_CANCELLED,
                "operation cancelled before transactional publish",
                inner_result.input_bytes,
                inner_result.output_bytes,
                std::chrono::duration<double>(Clock::now() - start).count());
            return KEPHIR2_CANCELLED;
        }

        kephir2::publish_directory_stage(
            stage,
            destination,
            destination_exists);

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_OK,
            success_message,
            inner_result.input_bytes,
            inner_result.output_bytes,
            elapsed);
        emit_done(
            forwarder,
            inner_result.output_bytes,
            inner_result.output_bytes);
        return KEPHIR2_OK;
    } catch (const std::exception& error) {
        kephir2::remove_directory_tree_noexcept(stage);
        const std::string_view message(error.what());
        const auto status = message.find("already exists") != std::string_view::npos
            ? KEPHIR2_OUTPUT_EXISTS
            : KEPHIR2_IO_ERROR;
        fill_result(
            result,
            status,
            message,
            inner_result.input_bytes,
            inner_result.output_bytes,
            std::chrono::duration<double>(Clock::now() - start).count());
        return status;
    } catch (...) {
        kephir2::remove_directory_tree_noexcept(stage);
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown transactional extraction error",
            inner_result.input_bytes,
            inner_result.output_bytes,
            std::chrono::duration<double>(Clock::now() - start).count());
        return KEPHIR2_INTERNAL_ERROR;
    }
}

} // namespace

extern "C" {

kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !archive_utf8 || !output_directory_utf8
        || !options_shape_valid(options)) {
        return kephir2_extract_indexed_payload(
            engine,
            archive_utf8,
            output_directory_utf8,
            options,
            result);
    }

    return run_transactional_extract(
        engine,
        archive_utf8,
        output_directory_utf8,
        options,
        result,
        "AUR2 indexed file-backed transactional extraction committed",
        [engine, archive_utf8](
            const char* destination_utf8,
            const kephir2_options_v1* forwarded,
            kephir2_result_v1* inner_result) {
            return kephir2_extract_indexed_payload(
                engine,
                archive_utf8,
                destination_utf8,
                forwarded,
                inner_result);
        });
}

kephir2_status kephir2_extract_selected(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_selection_v1* selection,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !archive_utf8 || !output_directory_utf8 || !selection
        || selection->struct_size < sizeof(kephir2_selection_v1)
        || !options_shape_valid(options)) {
        return kephir2_extract_selected_indexed_payload(
            engine,
            archive_utf8,
            output_directory_utf8,
            selection,
            options,
            result);
    }

    return run_transactional_extract(
        engine,
        archive_utf8,
        output_directory_utf8,
        options,
        result,
        "AUR2 indexed file-backed selective transactional extraction committed",
        [engine, archive_utf8, selection](
            const char* destination_utf8,
            const kephir2_options_v1* forwarded,
            kephir2_result_v1* inner_result) {
            return kephir2_extract_selected_indexed_payload(
                engine,
                archive_utf8,
                destination_utf8,
                selection,
                forwarded,
                inner_result);
        });
}

} // extern "C"
