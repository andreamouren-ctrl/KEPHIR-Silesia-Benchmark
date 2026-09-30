#include "kephir2/context_policy.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace kephir2 {
namespace {

constexpr std::size_t kDefaultContext = 512u * 1024u;
constexpr std::size_t kMediumContext = 4u * 1024u * 1024u;
constexpr std::size_t kLongContext = 8u * 1024u * 1024u;

constexpr std::size_t kQuarters = 4;
constexpr std::size_t kWindowsPerQuarter = 8;
constexpr std::size_t kWindowBytes = 8u * 1024u;

double entropy_from_counts(
    const std::array<std::uint64_t, 256>& counts,
    std::uint64_t total) {

    if (total == 0) return 0.0;

    const double n = static_cast<double>(total);
    double h = 0.0;

    for (const auto count : counts) {
        if (!count) continue;
        const double p = static_cast<double>(count) / n;
        h -= p * std::log2(p);
    }
    return h;
}

double sample_quarter_entropy(
    const ByteSource& input,
    std::uint64_t begin,
    std::uint64_t end,
    std::size_t& sampled_bytes,
    std::uint64_t& printable_bytes,
    std::vector<double>& window_entropies) {

    if (end <= begin) return 0.0;

    const std::uint64_t length = end - begin;
    std::array<std::uint64_t, 256> counts{};
    std::uint64_t total = 0;

    for (std::size_t part = 0; part < kWindowsPerQuarter; ++part) {
        const auto region_begin =
            begin + (length * part) / kWindowsPerQuarter;
        const auto region_end =
            begin + (length * (part + 1)) / kWindowsPerQuarter;

        if (region_end <= region_begin) continue;

        const auto region_length = region_end - region_begin;
        const auto want = static_cast<std::size_t>(
            std::min<std::uint64_t>(kWindowBytes, region_length));
        const auto offset =
            region_begin + (region_length - want) / 2u;

        std::vector<std::uint8_t> buffer(want);
        const auto got = input.read(offset, buffer);
        if (got != want) {
            throw std::runtime_error(
                "short read while sampling adaptive context");
        }

        std::array<std::uint64_t, 256> local_counts{};
        for (const auto b : buffer) {
            ++counts[b];
            ++local_counts[b];
            printable_bytes +=
                (b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127))
                ? 1u : 0u;
        }
        total += buffer.size();
        sampled_bytes += buffer.size();
        window_entropies.push_back(
            entropy_from_counts(local_counts, buffer.size()));
    }

    return entropy_from_counts(counts, total);
}

} // namespace

ContextPolicyDecision choose_adaptive_context(
    const ByteSource& input) {

    ContextPolicyDecision out{};

    if (input.size() <= kDefaultContext) {
        return out;
    }

    std::array<double, kQuarters> entropy{};
    std::uint64_t printable_bytes = 0;
    std::vector<double> window_entropies;
    window_entropies.reserve(kQuarters * kWindowsPerQuarter);

    for (std::size_t q = 0; q < kQuarters; ++q) {
        const auto begin =
            (input.size() * q) / kQuarters;
        const auto end =
            (input.size() * (q + 1)) / kQuarters;

        entropy[q] = sample_quarter_entropy(
            input,
            begin,
            end,
            out.sampled_bytes,
            printable_bytes,
            window_entropies);
    }

    const auto [min_it, max_it] =
        std::minmax_element(entropy.begin(), entropy.end());
    out.quarter_entropy_spread = *max_it - *min_it;

    if (!window_entropies.empty()) {
        double mean = 0.0;
        for (const auto value : window_entropies) {
            mean += value;
        }
        mean /= static_cast<double>(window_entropies.size());

        double variance = 0.0;
        for (const auto value : window_entropies) {
            const auto delta = value - mean;
            variance += delta * delta;
        }
        variance /= static_cast<double>(window_entropies.size());
        out.window_entropy_std = std::sqrt(variance);
    }

    if (out.sampled_bytes != 0) {
        out.sample_printable_fraction =
            static_cast<double>(printable_bytes)
            / static_cast<double>(out.sampled_bytes);
    }

    const bool large_heterogeneous =
        input.size() >= 16u * 1024u * 1024u
        && out.quarter_entropy_spread >= 0.50
        && out.window_entropy_std >= 0.50;

    const bool medium_printable_drift =
        input.size() >= 4u * 1024u * 1024u
        && input.size() < 8u * 1024u * 1024u
        && out.sample_printable_fraction >= 0.95
        && out.quarter_entropy_spread >= 0.50
        && out.window_entropy_std >= 0.20;

    std::size_t context = kDefaultContext;
    if (large_heterogeneous || medium_printable_drift) {
        context = kLongContext;
        out.force_parent_grain = true;
    } else if (out.quarter_entropy_spread < 0.10
        && out.window_entropy_std < 0.12) {
        context = kLongContext;
    } else if (out.quarter_entropy_spread >= 0.10
        && out.quarter_entropy_spread < 0.20) {
        context = kMediumContext;
    }

    out.inner_chunk_bytes = context;

    // Allocating more parent memory than the entire logical stream cannot
    // change segmentation, so cap only the parent buffer. The inner context
    // remains self-describing and can stay at the selected policy value.
    out.parent_bytes = static_cast<std::size_t>(
        std::min<std::uint64_t>(context, input.size()));

    if (out.parent_bytes == 0) {
        out.parent_bytes = kDefaultContext;
    }

    return out;
}

} // namespace kephir2
