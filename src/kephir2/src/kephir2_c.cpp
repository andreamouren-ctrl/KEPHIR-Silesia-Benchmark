#include "kephir2/kephir2_c.h"

#include <cstring>
#include <new>
#include <string_view>

struct kephir2_engine {
    uint32_t api_version{KEPHIR2_API_VERSION};
};

namespace {

void fill_result(
    kephir2_result_v1* result,
    kephir2_status status,
    std::string_view message) noexcept {
    if (!result) return;
    std::memset(result, 0, sizeof(*result));
    result->struct_size = sizeof(*result);
    result->status = status;
    const auto n = message.size() < sizeof(result->message)-1
        ? message.size()
        : sizeof(result->message)-1;
    if (n) std::memcpy(result->message, message.data(), n);
    result->message[n] = '\0';
}

bool valid_options(const kephir2_options_v1* options) noexcept {
    return !options || options->struct_size >= sizeof(kephir2_options_v1);
}

} // namespace

extern "C" {

uint32_t kephir2_api_version(void) {
    return KEPHIR2_API_VERSION;
}

const char* kephir2_engine_version(void) {
    return "2.0-dev";
}

kephir2_engine* kephir2_create(void) {
    try {
        return new kephir2_engine{};
    } catch (...) {
        return nullptr;
    }
}

void kephir2_destroy(kephir2_engine* engine) {
    delete engine;
}

kephir2_status kephir2_compress(
    kephir2_engine* engine,
    const char* input_utf8,
    const char* output_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !input_utf8 || !output_utf8 || !valid_options(options)) {
        fill_result(result, KEPHIR2_INVALID_ARGUMENT, "invalid KEPHIR 2 compression arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    fill_result(result, KEPHIR2_BACKEND_UNAVAILABLE,
        "KEPHIR 2 native compression backend is not wired yet");
    return KEPHIR2_BACKEND_UNAVAILABLE;
}

kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result) {

    if (!engine || !archive_utf8 || !output_directory_utf8 || !valid_options(options)) {
        fill_result(result, KEPHIR2_INVALID_ARGUMENT, "invalid KEPHIR 2 extraction arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    fill_result(result, KEPHIR2_BACKEND_UNAVAILABLE,
        "KEPHIR 2 native extraction backend is not wired yet");
    return KEPHIR2_BACKEND_UNAVAILABLE;
}

const char* kephir2_status_name(kephir2_status status) {
    switch (status) {
    case KEPHIR2_OK: return "OK";
    case KEPHIR2_CANCELLED: return "CANCELLED";
    case KEPHIR2_INVALID_ARGUMENT: return "INVALID_ARGUMENT";
    case KEPHIR2_INPUT_NOT_FOUND: return "INPUT_NOT_FOUND";
    case KEPHIR2_OUTPUT_EXISTS: return "OUTPUT_EXISTS";
    case KEPHIR2_IO_ERROR: return "IO_ERROR";
    case KEPHIR2_UNSUPPORTED_ARCHIVE: return "UNSUPPORTED_ARCHIVE";
    case KEPHIR2_CORRUPT_ARCHIVE: return "CORRUPT_ARCHIVE";
    case KEPHIR2_INTEGRITY_ERROR: return "INTEGRITY_ERROR";
    case KEPHIR2_BACKEND_UNAVAILABLE: return "BACKEND_UNAVAILABLE";
    case KEPHIR2_INTERNAL_ERROR: return "INTERNAL_ERROR";
    }
    return "UNKNOWN";
}

} // extern C
