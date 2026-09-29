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
constexpr std::size_t kWindowsPerQuarter = 4;
constexpr std::size_t kWindowBytes = 16u * 1024u;

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
    std::size_t& sampled_bytes) {

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

        for (const auto b : buffer) {
            ++counts[b];
        }
        total += buffer.size();
        sampled_bytes += buffer.size();
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

    for (std::size_t q = 0; q < kQuarters; ++q) {
        const auto begin =
            (input.size() * q) / kQuarters;
        const auto end =
            (input.size() * (q + 1)) / kQuarters;

        entropy[q] = sample_quarter_entropy(
            input,
            begin,
            end,
            out.sampled_bytes);
    }

    const auto [min_it, max_it] =
        std::minmax_element(entropy.begin(), entropy.end());
    out.quarter_entropy_spread = *max_it - *min_it;

    std::size_t context = kDefaultContext;
    if (out.quarter_entropy_spread < 0.10) {
        context = kLongContext;
    } else if (out.quarter_entropy_spread < 0.20) {
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
