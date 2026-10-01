#include "kephir2/kephir2_c.h"

#include <cstring>

extern "C" {

kephir2_status kephir2_get_capabilities(
    kephir2_engine* engine,
    kephir2_capabilities_v1* capabilities) {

    if (!engine || !capabilities
        || capabilities->struct_size < sizeof(kephir2_capabilities_v1)) {
        return KEPHIR2_INVALID_ARGUMENT;
    }

    std::memset(capabilities, 0, sizeof(*capabilities));
    capabilities->struct_size = sizeof(*capabilities);
    capabilities->api_version = KEPHIR2_API_VERSION;
    capabilities->engine_major = 2;
    capabilities->engine_minor = 0;
    capabilities->engine_patch = 0;
    capabilities->max_workers = 16;
    capabilities->capability_flags =
        KEPHIR2_CAP_COMPRESS_FILE |
        KEPHIR2_CAP_COMPRESS_DIRECTORY |
        KEPHIR2_CAP_EXTRACT |
        KEPHIR2_CAP_INSPECT |
        KEPHIR2_CAP_LIST_ENTRIES |
        KEPHIR2_CAP_EXTRACT_SELECTED |
        KEPHIR2_CAP_TEST_ARCHIVE |
        KEPHIR2_CAP_AUR2_READ |
        KEPHIR2_CAP_AUR2_WRITE |
        KEPHIR2_CAP_KPF1_LEGACY_READ |
        KEPHIR2_CAP_SEEK_INDEX |
        KEPHIR2_CAP_FILESYSTEM_METADATA |
        KEPHIR2_CAP_FOOTER_INTEGRITY |
        KEPHIR2_CAP_STREAM_CRC32 |
        KEPHIR2_CAP_PROGRESS_CALLBACK |
        KEPHIR2_CAP_CANCELLATION;
    capabilities->aur_read_major_min = 2;
    capabilities->aur_read_major_max = 2;
    capabilities->aur_write_major = 2;
    return KEPHIR2_OK;
}

} // extern "C"
