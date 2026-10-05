#include "kephir2/context_policy.hpp"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <span>
#include <vector>

namespace {

class MemorySource final : public kephir2::ByteSource {
public:
    explicit MemorySource(std::vector<std::uint8_t> data)
        : data_(std::move(data)) {}

    std::uint64_t size() const noexcept override {
        return data_.size();
    }

    std::size_t read(
        std::uint64_t offset,
        std::span<std::uint8_t> destination) const override {

        if (offset >= data_.size() || destination.empty()) return 0;
        const auto count = std::min<std::size_t>(
            destination.size(),
            data_.size() - static_cast<std::size_t>(offset));
        std::copy_n(
            data_.begin() + static_cast<std::ptrdiff_t>(offset),
            count,
            destination.begin());
        return count;
    }

private:
    std::vector<std::uint8_t> data_;
};

} // namespace

int main() {
    constexpr std::size_t MiB = 1024u * 1024u;

    std::vector<std::uint8_t> stable(8u * MiB);
    for (std::size_t i = 0; i < stable.size(); ++i) {
        stable[i] = static_cast<std::uint8_t>(
            "stable text-like payload\n"[i % 25]);
    }

    MemorySource stable_source(std::move(stable));
    const auto stable_plan =
        kephir2::choose_adaptive_context(stable_source);

    assert(stable_plan.inner_chunk_bytes == 8u * MiB);
    assert(stable_plan.parent_bytes == 8u * MiB);
    assert(stable_plan.sampled_bytes <= 256u * 1024u);
    assert(stable_plan.quarter_entropy_spread < 0.10);
    assert(stable_plan.window_entropy_std < 0.12);

    // Equal quarter-level entropy can hide strong local volatility. Alternate
    // low/high-entropy regions identically in every quarter: global spread
    // remains near zero, but the local volatility gate must reject 8 MiB.
    std::vector<std::uint8_t> volatile_local(8u * MiB, 0);
    constexpr std::size_t region = 256u * 1024u;
    for (std::size_t r = 0; r < volatile_local.size() / region; ++r) {
        if ((r & 1u) == 0) continue;
        const auto begin = r * region;
        const auto end = begin + region;
        for (std::size_t i = begin; i < end; ++i) {
            volatile_local[i] = static_cast<std::uint8_t>(i & 0xffu);
        }
    }

    MemorySource volatile_source(std::move(volatile_local));
    const auto volatile_plan =
        kephir2::choose_adaptive_context(volatile_source);

    assert(volatile_plan.quarter_entropy_spread < 0.10);
    assert(volatile_plan.window_entropy_std >= 0.12);
    assert(volatile_plan.inner_chunk_bytes == 512u * 1024u);

    std::vector<std::uint8_t> shifted(8u * MiB, 0);
    for (std::size_t i = 2u * MiB; i < 4u * MiB; ++i) {
        shifted[i] = static_cast<std::uint8_t>(i & 0xffu);
    }
    for (std::size_t i = 6u * MiB; i < 8u * MiB; ++i) {
        shifted[i] = static_cast<std::uint8_t>((i * 31u) & 0xffu);
    }

    MemorySource shifted_source(std::move(shifted));
    const auto shifted_plan =
        kephir2::choose_adaptive_context(shifted_source);

    assert(shifted_plan.inner_chunk_bytes == 512u * 1024u);
    assert(shifted_plan.sampled_bytes <= 256u * 1024u);
    assert(shifted_plan.quarter_entropy_spread >= 0.20);

    std::vector<std::uint8_t> small(128u * 1024u, 7);
    MemorySource small_source(std::move(small));
    const auto small_plan =
        kephir2::choose_adaptive_context(small_source);

    assert(small_plan.inner_chunk_bytes == 512u * 1024u);
    assert(small_plan.sampled_bytes == 0);

    return 0;
}
