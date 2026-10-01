#include "kephir2/native37_blob.hpp"

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

std::vector<std::uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unable to open input");
    return {
        std::istreambuf_iterator<char>(in),
        std::istreambuf_iterator<char>()
    };
}

std::vector<std::uint8_t> delta_lag(
    const std::vector<std::uint8_t>& input,
    std::size_t lag) {

    std::vector<std::uint8_t> out(input.size());
    for (std::size_t i = 0; i < input.size(); ++i) {
        out[i] = i < lag
            ? input[i]
            : static_cast<std::uint8_t>(input[i] - input[i - lag]);
    }
    return out;
}

std::vector<std::uint8_t> inv_delta(
    const std::vector<std::uint8_t>& input,
    std::size_t lag) {

    std::vector<std::uint8_t> out(input.size());
    for (std::size_t i = 0; i < input.size(); ++i) {
        out[i] = i < lag
            ? input[i]
            : static_cast<std::uint8_t>(input[i] + out[i - lag]);
    }
    return out;
}

std::vector<std::uint8_t> transpose(
    const std::vector<std::uint8_t>& input,
    std::size_t width) {

    const auto rows = input.size() / width;
    const auto main = rows * width;
    std::vector<std::uint8_t> out;
    out.reserve(input.size());
    for (std::size_t c = 0; c < width; ++c) {
        for (std::size_t i = c; i < main; i += width) {
            out.push_back(input[i]);
        }
    }
    out.insert(
        out.end(),
        input.begin() + static_cast<std::ptrdiff_t>(main),
        input.end());
    return out;
}

std::vector<std::uint8_t> inv_transpose(
    const std::vector<std::uint8_t>& input,
    std::size_t width) {

    const auto raw_length = input.size();
    const auto rows = raw_length / width;
    const auto main = rows * width;
    std::vector<std::uint8_t> out(raw_length);
    std::size_t k = 0;
    for (std::size_t c = 0; c < width; ++c) {
        for (std::size_t r = 0; r < rows; ++r) {
            out[r * width + c] = input[k++];
        }
    }
    for (std::size_t i = main; i < raw_length; ++i) {
        out[i] = input[k++];
    }
    return out;
}

struct Result {
    std::size_t lag{0};
    std::size_t bytes{0};
    double encode_seconds{0.0};
    double decode_seconds{0.0};
    bool roundtrip{false};
};

Result measure(
    const std::vector<std::uint8_t>& raw,
    std::size_t lag,
    std::size_t chunk_bytes) {

    std::vector<std::uint8_t> transformed;
    if (lag == 0) {
        transformed = raw;
    } else {
        transformed = transpose(delta_lag(raw, lag), lag);
    }

    const auto t0 = Clock::now();
    const auto blob = kephir2::native37::encode_aur2_blob(
        transformed,
        chunk_bytes);
    const auto t1 = Clock::now();

    const auto decoded = kephir2::native37::decode_aur2_blob(blob);
    std::vector<std::uint8_t> restored;
    if (lag == 0) {
        restored = decoded;
    } else {
        restored = inv_delta(inv_transpose(decoded, lag), lag);
    }
    const auto t2 = Clock::now();

    return {
        lag,
        blob.size(),
        std::chrono::duration<double>(t1 - t0).count(),
        std::chrono::duration<double>(t2 - t1).count(),
        restored == raw,
    };
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 3) {
        std::cerr << "usage: kephir2_stride_transform_oracle INPUT [chunk_kib]\n";
        return 2;
    }

    try {
        const std::filesystem::path input = argv[1];
        const std::size_t chunk_kib = argc == 3
            ? static_cast<std::size_t>(std::strtoull(argv[2], nullptr, 10))
            : 8192u;
        if (chunk_kib == 0) throw std::runtime_error("invalid chunk size");
        const std::size_t chunk_bytes = chunk_kib * 1024u;

        const auto raw = read_all(input);
        const std::vector<std::size_t> lags{
            0u, 2u, 4u, 16u, 256u, 512u, 1024u, 2048u, 4096u
        };

        std::vector<Result> results;
        for (const auto lag : lags) {
            if (lag != 0 && raw.size() < lag) continue;
            auto r = measure(raw, lag, chunk_bytes);
            if (!r.roundtrip) {
                throw std::runtime_error("stride transform roundtrip mismatch");
            }
            results.push_back(r);
            std::cout
                << "LAG=" << r.lag
                << " BYTES=" << r.bytes
                << " ENC_SECONDS=" << r.encode_seconds
                << " DEC_SECONDS=" << r.decode_seconds
                << " SHA_OK=1\n";
        }

        const auto best = std::min_element(
            results.begin(), results.end(),
            [](const auto& a, const auto& b) {
                if (a.bytes != b.bytes) return a.bytes < b.bytes;
                return a.lag < b.lag;
            });
        const auto fixed1024 = std::find_if(
            results.begin(), results.end(),
            [](const auto& r) { return r.lag == 1024u; });
        const auto raw_it = std::find_if(
            results.begin(), results.end(),
            [](const auto& r) { return r.lag == 0u; });

        std::cout << "RAW_BYTES=" << raw.size() << "\n";
        std::cout << "CHUNK_BYTES=" << chunk_bytes << "\n";
        std::cout << "BEST_LAG=" << best->lag << "\n";
        std::cout << "BEST_BYTES=" << best->bytes << "\n";
        if (fixed1024 != results.end()) {
            std::cout << "FIXED1024_BYTES=" << fixed1024->bytes << "\n";
            std::cout << "GAIN_VS_1024="
                      << static_cast<long long>(fixed1024->bytes)
                           - static_cast<long long>(best->bytes)
                      << "\n";
        }
        if (raw_it != results.end()) {
            std::cout << "RAW_AUR2_BYTES=" << raw_it->bytes << "\n";
            std::cout << "GAIN_VS_RAW="
                      << static_cast<long long>(raw_it->bytes)
                           - static_cast<long long>(best->bytes)
                      << "\n";
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << "\n";
        return 1;
    }
}
