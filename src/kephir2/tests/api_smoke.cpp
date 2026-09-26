#include "kephir2/kephir2_c.h"

#include <cassert>
#include <cstring>

int main() {
    assert(kephir2_api_version() == KEPHIR2_API_VERSION);
    assert(std::strcmp(kephir2_engine_version(), "2.0-dev") == 0);

    auto* engine = kephir2_create();
    assert(engine != nullptr);

    kephir2_options_v1 options{};
    options.struct_size = sizeof(options);
    options.profile = KEPHIR2_PROFILE_AUTO;
    options.verify_integrity = 1;
    options.allow_local_experience = 1;

    kephir2_result_v1 result{};
    result.struct_size = sizeof(result);

    const auto c = kephir2_compress(
        engine,
        "input",
        "output.kpf",
        &options,
        &result);

    assert(c == KEPHIR2_BACKEND_UNAVAILABLE);
    assert(result.status == KEPHIR2_BACKEND_UNAVAILABLE);
    assert(std::strcmp(
        kephir2_status_name(result.status),
        "BACKEND_UNAVAILABLE") == 0);

    kephir2_result_v1 invalid{};
    invalid.struct_size = sizeof(invalid);
    const auto bad = kephir2_compress(
        nullptr,
        "input",
        "output.kpf",
        &options,
        &invalid);
    assert(bad == KEPHIR2_INVALID_ARGUMENT);

    kephir2_destroy(engine);
    return 0;
}
