#include "kephir2/kephir2_c.h"

#include "kephir2/archive.hpp"
#include "kephir2/auto_routing.hpp"
#include "kephir2/execution.hpp"
#include "kephir2/native_k75.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <new>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

struct kephir2_engine {
    uint32_t api_version{KEPHIR2_API_VERSION};
    kephir2::NativeK75Backend backend{};
    kephir2::ArchiveExecutor executor{};
    kephir2::ProductionAutoResolver resolver{};
};

namespace {

using Clock = std::chrono::steady_clock;

struct OptionsView {
    kephir2_profile profile{KEPHIR2_PROFILE_AUTO};
    uint32_t workers{0};
    bool verify_integrity{true};
    bool overwrite_output{false};
    bool allow_local_experience{true};
    kephir2_progress_callback progress_callback{nullptr};
    kephir2_cancel_callback cancel_callback{nullptr};
    void* user_data{nullptr};
};

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

    const auto n = std::min(
        message.size(),
        sizeof(result->message) - 1);
    if (n) std::memcpy(result->message, message.data(), n);
    result->message[n] = '\0';
}

bool valid_options(const kephir2_options_v1* options) noexcept {
    if (!options) return true;
    if (options->struct_size < sizeof(kephir2_options_v1)) return false;
    return options->profile >= KEPHIR2_PROFILE_AUTO
        && options->profile <= KEPHIR2_PROFILE_MAX;
}

OptionsView read_options(const kephir2_options_v1* options) noexcept {
    OptionsView out;
    if (!options) return out;

    out.profile = options->profile;
    out.workers = options->workers;
    out.verify_integrity = options->verify_integrity != 0;
    out.overwrite_output = options->overwrite_output != 0;
    out.allow_local_experience = options->allow_local_experience != 0;
    out.progress_callback = options->progress_callback;
    out.cancel_callback = options->cancel_callback;
    out.user_data = options->user_data;
    return out;
}

kephir2::Profile to_profile(kephir2_profile profile) {
    using kephir2::Profile;
    switch (profile) {
    case KEPHIR2_PROFILE_FAST: return Profile::Fast;
    case KEPHIR2_PROFILE_BALANCED: return Profile::Balanced;
    case KEPHIR2_PROFILE_MAX: return Profile::Max;
    case KEPHIR2_PROFILE_AUTO:
    default:
        return Profile::Auto;
    }
}

kephir2::BackendOptions to_backend_options(
    const OptionsView& options,
    const kephir2::OperationContext* operation = nullptr) {

    kephir2::BackendOptions out;
    out.workers = options.workers;
    out.allow_local_experience = options.allow_local_experience;
    out.operation = operation;
    return out;
}

kephir2_phase to_c_phase(kephir2::OperationPhase phase) noexcept {
    using kephir2::OperationPhase;
    switch (phase) {
    case OperationPhase::Idle: return KEPHIR2_PHASE_IDLE;
    case OperationPhase::Scanning: return KEPHIR2_PHASE_SCANNING;
    case OperationPhase::Analyzing: return KEPHIR2_PHASE_ANALYZING;
    case OperationPhase::Planning: return KEPHIR2_PHASE_PLANNING;
    case OperationPhase::Packing: return KEPHIR2_PHASE_PACKING;
    case OperationPhase::Compressing: return KEPHIR2_PHASE_COMPRESSING;
    case OperationPhase::Writing: return KEPHIR2_PHASE_WRITING;
    case OperationPhase::Verifying: return KEPHIR2_PHASE_VERIFYING;
    case OperationPhase::Extracting: return KEPHIR2_PHASE_EXTRACTING;
    case OperationPhase::Done: return KEPHIR2_PHASE_DONE;
    }
    return KEPHIR2_PHASE_IDLE;
}

kephir2::OperationContext make_backend_operation_context(
    const OptionsView& options,
    bool report_progress) {

    kephir2::OperationContext::ProgressCallback progress;
    if (report_progress && options.progress_callback) {
        progress = [&options](const kephir2::OperationProgress& p) {
            kephir2_progress_v1 out{};
            out.struct_size = sizeof(out);
            out.phase = to_c_phase(p.phase);
            out.fraction = std::clamp(p.fraction, 0.0, 1.0);
            out.processed_bytes = p.processed_bytes;
            out.total_bytes = p.total_bytes;
            out.current_path_utf8 =
                p.current_path.empty() ? nullptr : p.current_path.c_str();
            options.progress_callback(&out, options.user_data);
        };
    }

    kephir2::OperationContext::CancelCallback cancel;
    if (options.cancel_callback) {
        cancel = [&options]() {
            return options.cancel_callback(options.user_data) != 0;
        };
    }

    return kephir2::OperationContext(
        std::move(progress),
        std::move(cancel));
}

std::filesystem::path from_utf8(const char* value) {
    const std::string text(value ? value : "");
    return std::filesystem::u8path(text.begin(), text.end());
}

std::uint64_t input_logical_bytes(const std::filesystem::path& input) {
    if (std::filesystem::is_regular_file(input)) {
        return std::filesystem::file_size(input);
    }
    if (std::filesystem::is_directory(input)) {
        std::uint64_t total = 0;
        for (const auto& path : kephir2::collect_directory_files(input)) {
            total += std::filesystem::file_size(path);
        }
        return total;
    }
    return 0;
}

void emit_progress(
    const OptionsView& options,
    kephir2_phase phase,
    double fraction,
    std::uint64_t processed,
    std::uint64_t total,
    const std::string& current_path = {}) {

    if (!options.progress_callback) return;

    kephir2_progress_v1 progress{};
    progress.struct_size = sizeof(progress);
    progress.phase = phase;
    progress.fraction = std::clamp(fraction, 0.0, 1.0);
    progress.processed_bytes = processed;
    progress.total_bytes = total;
    progress.current_path_utf8 =
        current_path.empty() ? nullptr : current_path.c_str();

    options.progress_callback(&progress, options.user_data);
}

bool cancelled(const OptionsView& options) noexcept {
    return options.cancel_callback
        && options.cancel_callback(options.user_data) != 0;
}

void throw_if_cancelled(const OptionsView& options) {
    if (cancelled(options)) {
        throw kephir2::OperationCancelled{};
    }
}

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unable to open archive");

    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

void write_all(
    const std::filesystem::path& path,
    std::span<const std::uint8_t> bytes) {

    const auto parent = path.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("unable to create output");

    if (!bytes.empty()) {
        out.write(
            reinterpret_cast<const char*>(bytes.data()),
            static_cast<std::streamsize>(bytes.size()));
    }
    out.flush();
    if (!out) throw std::runtime_error("unable to write output");
}

std::filesystem::path temporary_output_path(
    const std::filesystem::path& destination) {

    const auto ticks = static_cast<unsigned long long>(
        Clock::now().time_since_epoch().count());

    auto parent = destination.parent_path();
    if (parent.empty()) parent = ".";

    return parent / (
        destination.filename().string()
        + ".kephir2.tmp."
        + std::to_string(ticks));
}

void replace_output_atomically(
    const std::filesystem::path& temporary,
    const std::filesystem::path& destination,
    bool overwrite) {

    if (!overwrite && std::filesystem::exists(destination)) {
        throw std::runtime_error("output already exists");
    }

#ifdef _WIN32
    const DWORD flags = overwrite
        ? (MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)
        : MOVEFILE_WRITE_THROUGH;

    if (!MoveFileExW(
            temporary.c_str(),
            destination.c_str(),
            flags)) {
        throw std::runtime_error("unable to atomically publish output");
    }
#else
    if (!overwrite && std::filesystem::exists(destination)) {
        throw std::runtime_error("output already exists");
    }

    std::filesystem::rename(temporary, destination);
#endif
}

bool files_equal(
    const std::filesystem::path& a,
    const std::filesystem::path& b) {

    if (!std::filesystem::is_regular_file(a)
        || !std::filesystem::is_regular_file(b)
        || std::filesystem::file_size(a) != std::filesystem::file_size(b)) {
        return false;
    }

    std::ifstream left(a, std::ios::binary);
    std::ifstream right(b, std::ios::binary);
    if (!left || !right) return false;

    constexpr std::size_t kBlock = 1024u * 1024u;
    std::vector<char> x(kBlock), y(kBlock);

    while (left && right) {
        left.read(x.data(), static_cast<std::streamsize>(x.size()));
        right.read(y.data(), static_cast<std::streamsize>(y.size()));

        const auto lx = left.gcount();
        const auto ly = right.gcount();
        if (lx != ly) return false;
        if (lx == 0) break;

        if (!std::equal(x.begin(), x.begin() + lx, y.begin())) {
            return false;
        }
    }
    return true;
}

bool trees_equal(
    const std::filesystem::path& a,
    const std::filesystem::path& b) {

    const auto af = kephir2::collect_directory_files(a);
    const auto bf = kephir2::collect_directory_files(b);

    if (af.size() != bf.size()) return false;

    for (std::size_t i = 0; i < af.size(); ++i) {
        const auto ar = af[i].lexically_relative(a);
        const auto br = bf[i].lexically_relative(b);
        if (ar.generic_string() != br.generic_string()) return false;
        if (!files_equal(af[i], bf[i])) return false;
    }
    return true;
}

class TempDirectory {
public:
    explicit TempDirectory(std::filesystem::path path)
        : path_(std::move(path)) {
        std::filesystem::create_directories(path_);
    }

    ~TempDirectory() {
        std::error_code ec;
        std::filesystem::remove_all(path_, ec);
    }

    [[nodiscard]] const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    std::filesystem::path path_;
};

TempDirectory make_verify_directory() {
    const auto ticks = static_cast<unsigned long long>(
        Clock::now().time_since_epoch().count());

    return TempDirectory(
        std::filesystem::temp_directory_path()
        / ("kephir2_verify_" + std::to_string(ticks)));
}

bool verify_roundtrip(
    kephir2_engine& engine,
    const std::filesystem::path& input,
    std::span<const std::uint8_t> archive,
    const kephir2::BackendOptions& backend_options) {

    auto temp = make_verify_directory();

    if (std::filesystem::is_regular_file(input)) {
        engine.executor.extract_file(
            archive,
            temp.path(),
            engine.backend,
            backend_options);

        return files_equal(
            input,
            temp.path() / input.filename());
    }

    engine.executor.extract_directory(
        archive,
        temp.path(),
        engine.backend,
        backend_options);

    return trees_equal(input, temp.path());
}

kephir2_status map_exception(
    const std::exception& error,
    kephir2_result_v1* result,
    std::uint64_t input_bytes,
    std::uint64_t output_bytes,
    double elapsed_seconds) noexcept {

    const std::string message = error.what();

    if (dynamic_cast<const kephir2::OperationCancelled*>(&error) != nullptr
        || message == "KEPHIR2_CANCELLED"
        || message == "KEPHIR operation cancelled") {
        fill_result(
            result,
            KEPHIR2_CANCELLED,
            "operation cancelled",
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_CANCELLED;
    }

    if (message.find("output already exists") != std::string::npos) {
        fill_result(
            result,
            KEPHIR2_OUTPUT_EXISTS,
            message,
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_OUTPUT_EXISTS;
    }

    if (message.find("not KPF1") != std::string::npos
        || message.find("not a KPF1") != std::string::npos
        || message.find("unsupported") != std::string::npos) {
        fill_result(
            result,
            KEPHIR2_UNSUPPORTED_ARCHIVE,
            message,
            input_bytes,
            output_bytes,
            elapsed_seconds);
        return KEPHIR2_UNSUPPORTED_ARCHIVE;
    }

    if (message.find("truncated") != std::string::npos
        || message.find("corrupt") != std::string::npos
        || message.find("mismatch") != std::string::npos
        || message.find("unsafe archive path") != std::string::npos) {
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

uint32_t kephir2_api_version(void) {
    return KEPHIR2_API_VERSION;
}

const char* kephir2_engine_version(void) {
    return "2.0-dev-native";
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
    const kephir2_options_v1* options_raw,
    kephir2_result_v1* result) {

    const auto start = Clock::now();
    std::uint64_t input_bytes = 0;
    std::uint64_t output_bytes = 0;
    std::filesystem::path temporary;

    if (!engine || !input_utf8 || !output_utf8 || !valid_options(options_raw)) {
        fill_result(
            result,
            KEPHIR2_INVALID_ARGUMENT,
            "invalid KEPHIR 2 compression arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto options = read_options(options_raw);
    const auto input = from_utf8(input_utf8);
    const auto output = from_utf8(output_utf8);

    try {
        if (!std::filesystem::exists(input)) {
            fill_result(
                result,
                KEPHIR2_INPUT_NOT_FOUND,
                "compression input not found");
            return KEPHIR2_INPUT_NOT_FOUND;
        }

        if (!std::filesystem::is_regular_file(input)
            && !std::filesystem::is_directory(input)) {
            fill_result(
                result,
                KEPHIR2_INVALID_ARGUMENT,
                "compression input must be a file or directory");
            return KEPHIR2_INVALID_ARGUMENT;
        }

        if (!options.overwrite_output && std::filesystem::exists(output)) {
            fill_result(
                result,
                KEPHIR2_OUTPUT_EXISTS,
                "output already exists");
            return KEPHIR2_OUTPUT_EXISTS;
        }

        input_bytes = input_logical_bytes(input);
        const auto input_string = input.generic_string();

        emit_progress(
            options,
            KEPHIR2_PHASE_SCANNING,
            0.0,
            0,
            input_bytes,
            input_string);
        throw_if_cancelled(options);

        auto backend_operation =
            make_backend_operation_context(options, true);
        auto routing_operation =
            make_backend_operation_context(options, false);

        const auto backend_options =
            to_backend_options(options, &backend_operation);
        const auto routing_backend_options =
            to_backend_options(options, &routing_operation);

        kephir2::ByteBuffer archive;

        if (std::filesystem::is_directory(input)) {
            emit_progress(
                options,
                KEPHIR2_PHASE_ANALYZING,
                0.05,
                0,
                input_bytes,
                input_string);
            throw_if_cancelled(options);

            emit_progress(
                options,
                KEPHIR2_PHASE_PLANNING,
                0.10,
                0,
                input_bytes,
                input_string);

            const auto resolved = engine->resolver.resolve(
                input,
                engine->backend,
                to_profile(options.profile),
                routing_backend_options);

            throw_if_cancelled(options);

            emit_progress(
                options,
                KEPHIR2_PHASE_PACKING,
                0.20,
                0,
                input_bytes,
                input_string);

            emit_progress(
                options,
                KEPHIR2_PHASE_COMPRESSING,
                0.25,
                0,
                input_bytes,
                input_string);

            archive = engine->executor.compress_directory(
                input,
                engine->backend,
                backend_options,
                resolved.strategy.layout);
        } else {
            emit_progress(
                options,
                KEPHIR2_PHASE_COMPRESSING,
                0.15,
                0,
                input_bytes,
                input_string);

            archive = engine->executor.compress_file(
                input,
                engine->backend,
                backend_options);
        }

        throw_if_cancelled(options);
        output_bytes = archive.size();

        if (options.verify_integrity) {
            emit_progress(
                options,
                KEPHIR2_PHASE_VERIFYING,
                0.80,
                input_bytes,
                input_bytes,
                input_string);

            if (!verify_roundtrip(
                    *engine,
                    input,
                    archive,
                    backend_options)) {
                const auto elapsed = std::chrono::duration<double>(
                    Clock::now() - start).count();
                fill_result(
                    result,
                    KEPHIR2_INTEGRITY_ERROR,
                    "lossless verification failed",
                    input_bytes,
                    output_bytes,
                    elapsed);
                return KEPHIR2_INTEGRITY_ERROR;
            }
        }

        throw_if_cancelled(options);

        emit_progress(
            options,
            KEPHIR2_PHASE_WRITING,
            0.92,
            input_bytes,
            input_bytes,
            output.generic_string());

        temporary = temporary_output_path(output);
        write_all(temporary, archive);
        replace_output_atomically(
            temporary,
            output,
            options.overwrite_output);
        temporary.clear();

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        emit_progress(
            options,
            KEPHIR2_PHASE_DONE,
            1.0,
            input_bytes,
            input_bytes,
            output.generic_string());

        fill_result(
            result,
            KEPHIR2_OK,
            "compression completed",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_OK;

    } catch (const std::exception& error) {
        if (!temporary.empty()) {
            std::error_code ec;
            std::filesystem::remove(temporary, ec);
        }

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        return map_exception(
            error,
            result,
            input_bytes,
            output_bytes,
            elapsed);
    } catch (...) {
        if (!temporary.empty()) {
            std::error_code ec;
            std::filesystem::remove(temporary, ec);
        }

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown KEPHIR 2 compression error",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }
}

kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options_raw,
    kephir2_result_v1* result) {

    const auto start = Clock::now();
    std::uint64_t input_bytes = 0;
    std::uint64_t output_bytes = 0;

    if (!engine || !archive_utf8 || !output_directory_utf8
        || !valid_options(options_raw)) {
        fill_result(
            result,
            KEPHIR2_INVALID_ARGUMENT,
            "invalid KEPHIR 2 extraction arguments");
        return KEPHIR2_INVALID_ARGUMENT;
    }

    const auto options = read_options(options_raw);
    const auto archive_path = from_utf8(archive_utf8);
    const auto output = from_utf8(output_directory_utf8);

    try {
        if (!std::filesystem::is_regular_file(archive_path)) {
            fill_result(
                result,
                KEPHIR2_INPUT_NOT_FOUND,
                "archive not found");
            return KEPHIR2_INPUT_NOT_FOUND;
        }

        if (std::filesystem::exists(output)
            && !options.overwrite_output
            && !std::filesystem::is_empty(output)) {
            fill_result(
                result,
                KEPHIR2_OUTPUT_EXISTS,
                "output directory is not empty");
            return KEPHIR2_OUTPUT_EXISTS;
        }

        const auto archive = read_all(archive_path);
        input_bytes = archive.size();

        if (archive.size() < 5
            || archive[0] != 'K'
            || archive[1] != 'P'
            || archive[2] != 'F'
            || archive[3] != '1') {
            fill_result(
                result,
                KEPHIR2_UNSUPPORTED_ARCHIVE,
                "not a KPF1 archive",
                input_bytes);
            return KEPHIR2_UNSUPPORTED_ARCHIVE;
        }

        emit_progress(
            options,
            KEPHIR2_PHASE_EXTRACTING,
            0.0,
            0,
            input_bytes,
            archive_path.generic_string());
        throw_if_cancelled(options);

        auto backend_operation =
            make_backend_operation_context(options, true);
        const auto backend_options =
            to_backend_options(options, &backend_operation);

        if (archive[4] == static_cast<std::uint8_t>(kephir2::Kpf1Kind::File)) {
            const auto envelope = kephir2::decode_kpf1_file(archive);
            output_bytes = 0;
            engine->executor.extract_file(
                archive,
                output,
                engine->backend,
                backend_options);
        } else if (
            archive[4] == static_cast<std::uint8_t>(kephir2::Kpf1Kind::Directory)) {

            const auto envelope = kephir2::decode_kpf1_directory(archive);
            for (const auto& group : envelope.groups) {
                output_bytes += group.raw_length;
            }

            engine->executor.extract_directory(
                archive,
                output,
                engine->backend,
                backend_options);
        } else {
            fill_result(
                result,
                KEPHIR2_UNSUPPORTED_ARCHIVE,
                "unknown KPF1 archive kind",
                input_bytes);
            return KEPHIR2_UNSUPPORTED_ARCHIVE;
        }

        throw_if_cancelled(options);

        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        emit_progress(
            options,
            KEPHIR2_PHASE_DONE,
            1.0,
            input_bytes,
            input_bytes,
            output.generic_string());

        fill_result(
            result,
            KEPHIR2_OK,
            "extraction completed",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_OK;

    } catch (const std::exception& error) {
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        return map_exception(
            error,
            result,
            input_bytes,
            output_bytes,
            elapsed);
    } catch (...) {
        const auto elapsed = std::chrono::duration<double>(
            Clock::now() - start).count();

        fill_result(
            result,
            KEPHIR2_INTERNAL_ERROR,
            "unknown KEPHIR 2 extraction error",
            input_bytes,
            output_bytes,
            elapsed);
        return KEPHIR2_INTERNAL_ERROR;
    }
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

} // extern "C"
