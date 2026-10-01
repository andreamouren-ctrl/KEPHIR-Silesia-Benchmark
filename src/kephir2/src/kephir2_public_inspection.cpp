#include "kephir2/kephir2_c.h"

#include "kephir2/aur2_indexed_file.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <string>
#include <string_view>

extern "C" {
kephir2_status kephir2_inspect_scan(
    kephir2_engine*, const char*, kephir2_archive_info_v1*);
kephir2_status kephir2_list_entries_scan(
    kephir2_engine*, const char*, kephir2_entry_callback, void*);
kephir2_status kephir2_test_archive_scan(
    kephir2_engine*, const char*, const kephir2_options_v1*, kephir2_result_v1*);
}

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

kephir2_status classify_error(std::string_view message) noexcept {
    if (message.find("seek-index") != std::string_view::npos
        || message.find("SEEK_INDEX") != std::string_view::npos
        || message.find("TOC") != std::string_view::npos
        || message.find("truncated") != std::string_view::npos
        || message.find("mismatch") != std::string_view::npos
        || message.find("duplicate") != std::string_view::npos
        || message.find("missing") != std::string_view::npos
        || message.find("unknown") != std::string_view::npos
        || message.find("gap") != std::string_view::npos
        || message.find("overlap") != std::string_view::npos
        || message.find("exceeds") != std::string_view::npos
        || message.find("does not") != std::string_view::npos) {
        return KEPHIR2_CORRUPT_ARCHIVE;
    }
    if (message.find("not an AUR2") != std::string_view::npos
        || message.find("unsupported") != std::string_view::npos) {
        return KEPHIR2_UNSUPPORTED_ARCHIVE;
    }
    return KEPHIR2_IO_ERROR;
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

void copy_info(
    const kephir2::aur2::ArchiveInfo& native,
    kephir2_archive_info_v1* info) {

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
}

} // namespace

extern "C" {

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
        if (!kephir2::aur2::has_seek_index_file(path)) {
            return kephir2_inspect_scan(engine, archive_utf8, info);
        }
        copy_info(kephir2::aur2::inspect_indexed_file(path), info);
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
        if (!kephir2::aur2::has_seek_index_file(path)) {
            return kephir2_list_entries_scan(
                engine, archive_utf8, callback, user_data);
        }

        const auto entries = kephir2::aur2::list_indexed_file(path);
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
            if (callback(&entry, user_data) != 0) break;
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

    if (!engine || !archive_utf8) {
        return kephir2_test_archive_scan(
            engine, archive_utf8, options, result);
    }

    const auto path = from_utf8(archive_utf8);
    if (!std::filesystem::is_regular_file(path)) {
        return kephir2_test_archive_scan(
            engine, archive_utf8, options, result);
    }

    const auto start = Clock::now();
    try {
        if (kephir2::aur2::has_seek_index_file(path)) {
            kephir2::aur2::validate_seek_index_file(path);
        }
    } catch (const std::exception& error) {
        const auto status = classify_error(error.what());
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        std::uint64_t bytes = 0;
        std::error_code ec;
        bytes = std::filesystem::file_size(path, ec);
        if (ec) bytes = 0;
        fill_result(result, status, error.what(), bytes, 0, elapsed);
        return status;
    } catch (...) {
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();
        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown AUR2 seek-index validation error",
            0,
            0,
            elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }

    return kephir2_test_archive_scan(
        engine, archive_utf8, options, result);
}

} // extern "C"
