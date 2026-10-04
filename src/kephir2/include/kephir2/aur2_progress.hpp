#pragma once

#include "kephir2/backend.hpp"
#include "kephir2/operation.hpp"

#include <cstdint>

namespace kephir2::aur2 {

// Remaps one backend stream's local [0,1] progress into a monotonic archive-
// level interval. Units are logical output bytes so full and selective public
// extraction keep stable processed_bytes/total_bytes semantics across streams.
class StreamProgressAdapter final {
public:
    StreamProgressAdapter(
        const BackendOptions& base,
        std::uint64_t completed_units,
        std::uint64_t stream_units,
        std::uint64_t total_units);

    [[nodiscard]] BackendOptions options(const BackendOptions& base) noexcept;

private:
    OperationContext context_{};
    bool enabled_{false};
};

} // namespace kephir2::aur2
