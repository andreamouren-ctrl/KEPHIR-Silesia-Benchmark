#include "kephir2/kephir2_c.h"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

kephir2_profile parse_profile(const std::string& value) {
    if (value == "auto") return KEPHIR2_PROFILE_AUTO;
    if (value == "fast") return KEPHIR2_PROFILE_FAST;
    if (value == "balanced") return KEPHIR2_PROFILE_BALANCED;
    if (value == "max") return KEPHIR2_PROFILE_MAX;
    throw std::runtime_error("unknown profile");
}

void print_result(const kephir2_result_v1& result) {
    std::cout
        << "STATUS=" << kephir2_status_name(result.status) << "\n"
        << "INPUT_BYTES=" << result.input_bytes << "\n"
        << "OUTPUT_BYTES=" << result.output_bytes << "\n"
        << "SECONDS=" << result.elapsed_seconds << "\n"
        << "MESSAGE=" << result.message << "\n";
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 5 || argc > 7) {
        std::cerr
            << "usage: kephir2_c_api_cli <c|d> <auto|fast|balanced|max> "
            << "<input> <output> [workers] [verify]\n";
        return 2;
    }

    try {
        const std::string mode = argv[1];
        const auto profile = parse_profile(argv[2]);
        const auto workers = argc >= 6
            ? static_cast<std::uint32_t>(std::strtoul(argv[5], nullptr, 10))
            : 1u;
        const bool verify = argc >= 7
            ? std::strtoul(argv[6], nullptr, 10) != 0
            : true;

        auto* engine = kephir2_create();
        if (!engine) {
            std::cerr << "unable to create engine\n";
            return 1;
        }

        kephir2_options_v1 options{};
        options.struct_size = sizeof(options);
        options.profile = profile;
        options.workers = workers;
        options.verify_integrity = verify ? 1 : 0;
        options.overwrite_output = 1;
        options.allow_local_experience = 0;

        kephir2_result_v1 result{};
        result.struct_size = sizeof(result);

        kephir2_status status = KEPHIR2_INVALID_ARGUMENT;
        if (mode == "c") {
            status = kephir2_compress(
                engine,
                argv[3],
                argv[4],
                &options,
                &result);
        } else if (mode == "d") {
            status = kephir2_extract(
                engine,
                argv[3],
                argv[4],
                &options,
                &result);
        } else {
            kephir2_destroy(engine);
            std::cerr << "unknown mode\n";
            return 2;
        }

        print_result(result);
        kephir2_destroy(engine);
        return status == KEPHIR2_OK ? 0 : 1;
    } catch (const std::exception& e) {
        std::cerr << "ERROR=" << e.what() << "\n";
        return 1;
    }
}
