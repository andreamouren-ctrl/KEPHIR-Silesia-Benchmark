#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(KEPHIR2_BUILD_DLL)
#  define KEPHIR2_API __declspec(dllexport)
#elif defined(_WIN32)
#  define KEPHIR2_API __declspec(dllimport)
#else
#  define KEPHIR2_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define KEPHIR2_API_VERSION 1u

typedef struct kephir2_engine kephir2_engine;

typedef enum kephir2_status {
    KEPHIR2_OK = 0,
    KEPHIR2_CANCELLED = 1,
    KEPHIR2_INVALID_ARGUMENT = 2,
    KEPHIR2_INPUT_NOT_FOUND = 3,
    KEPHIR2_OUTPUT_EXISTS = 4,
    KEPHIR2_IO_ERROR = 5,
    KEPHIR2_UNSUPPORTED_ARCHIVE = 6,
    KEPHIR2_CORRUPT_ARCHIVE = 7,
    KEPHIR2_INTEGRITY_ERROR = 8,
    KEPHIR2_BACKEND_UNAVAILABLE = 9,
    KEPHIR2_INTERNAL_ERROR = 10
} kephir2_status;

typedef enum kephir2_profile {
    KEPHIR2_PROFILE_AUTO = 0,
    KEPHIR2_PROFILE_FAST = 1,
    KEPHIR2_PROFILE_BALANCED = 2,
    KEPHIR2_PROFILE_MAX = 3
} kephir2_profile;

typedef enum kephir2_phase {
    KEPHIR2_PHASE_IDLE = 0,
    KEPHIR2_PHASE_SCANNING = 1,
    KEPHIR2_PHASE_ANALYZING = 2,
    KEPHIR2_PHASE_PLANNING = 3,
    KEPHIR2_PHASE_PACKING = 4,
    KEPHIR2_PHASE_COMPRESSING = 5,
    KEPHIR2_PHASE_WRITING = 6,
    KEPHIR2_PHASE_VERIFYING = 7,
    KEPHIR2_PHASE_EXTRACTING = 8,
    KEPHIR2_PHASE_DONE = 9
} kephir2_phase;

typedef struct kephir2_progress_v1 {
    uint32_t struct_size;
    kephir2_phase phase;
    double fraction;
    uint64_t processed_bytes;
    uint64_t total_bytes;
    const char* current_path_utf8;
} kephir2_progress_v1;

typedef void (*kephir2_progress_callback)(const kephir2_progress_v1* progress, void* user_data);
typedef int (*kephir2_cancel_callback)(void* user_data);

typedef struct kephir2_options_v1 {
    uint32_t struct_size;
    kephir2_profile profile;
    uint32_t workers;
    int verify_integrity;
    int overwrite_output;
    int allow_local_experience;
    kephir2_progress_callback progress_callback;
    kephir2_cancel_callback cancel_callback;
    void* user_data;
} kephir2_options_v1;

typedef struct kephir2_result_v1 {
    uint32_t struct_size;
    kephir2_status status;
    uint64_t input_bytes;
    uint64_t output_bytes;
    double elapsed_seconds;
    char message[512];
} kephir2_result_v1;

typedef enum kephir2_entry_type {
    KEPHIR2_ENTRY_FILE = 0,
    KEPHIR2_ENTRY_DIRECTORY = 1
} kephir2_entry_type;

typedef struct kephir2_archive_info_v1 {
    uint32_t struct_size;
    uint32_t container_major;
    uint32_t container_minor;
    uint32_t codec_major;
    uint32_t codec_minor;
    uint64_t feature_flags;
    uint64_t entry_count;
    uint64_t logical_bytes;
    uint64_t archive_bytes;
    uint64_t stream_count;
    int is_encrypted;
    int integrity_available;
} kephir2_archive_info_v1;

typedef struct kephir2_entry_info_v1 {
    uint32_t struct_size;
    uint64_t entry_id;
    kephir2_entry_type type;
    uint64_t logical_size;
    uint64_t stream_id;
    uint64_t stream_offset;
    uint32_t attributes;
    int64_t mtime_unix_ns;
    const char* path_utf8;
} kephir2_entry_info_v1;

typedef int (*kephir2_entry_callback)(
    const kephir2_entry_info_v1* entry,
    void* user_data);

typedef struct kephir2_selection_v1 {
    uint32_t struct_size;
    const uint64_t* entry_ids;
    size_t entry_count;
} kephir2_selection_v1;

KEPHIR2_API uint32_t kephir2_api_version(void);
KEPHIR2_API const char* kephir2_engine_version(void);
KEPHIR2_API kephir2_engine* kephir2_create(void);
KEPHIR2_API void kephir2_destroy(kephir2_engine* engine);

KEPHIR2_API void kephir2_options_init_v1(
    kephir2_options_v1* options);

KEPHIR2_API kephir2_status kephir2_compress(
    kephir2_engine* engine,
    const char* input_utf8,
    const char* output_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

KEPHIR2_API kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

/* AUR Container v2 read-side API. These calls do not mutate the archive. */
KEPHIR2_API kephir2_status kephir2_inspect(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_archive_info_v1* info);

KEPHIR2_API kephir2_status kephir2_list_entries(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_entry_callback callback,
    void* user_data);

KEPHIR2_API kephir2_status kephir2_test_archive(
    kephir2_engine* engine,
    const char* archive_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

KEPHIR2_API kephir2_status kephir2_extract_selected(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_selection_v1* selection,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

KEPHIR2_API const char* kephir2_status_name(kephir2_status status);

#ifdef __cplusplus
}
#endif
