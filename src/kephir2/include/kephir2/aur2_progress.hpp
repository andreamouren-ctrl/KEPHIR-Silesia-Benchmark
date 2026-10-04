#pragma once

#include "kephir2/backend.hpp"
#include "kephir2/operation.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <utility>

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
        std::uint64_t total_units) {

        const auto* parent = base.operation;
        enabled_ = parent != nullptr;
        if (!enabled_) return;

        context_ = OperationContext(
            [parent, completed_units, stream_units, total_units](
                const OperationProgress& source) {

                const double local = std::clamp(source.fraction, 0.0, 1.0);
                std::uint64_t partial = 0;
                if (local >= 1.0) {
                    partial = stream_units;
                } else if (local > 0.0) {
                    const long double scaled =
                        static_cast<long double>(stream_units)
                        * static_cast<long double>(local);
                    partial = static_cast<std::uint64_t>(scaled);
                    if (partial > stream_units) partial = stream_units;
                }

                std::uint64_t processed = completed_units;
                if (partial > std::numeric_limits<std::uint64_t>::max() - processed) {
                    processed = std::numeric_limits<std::uint64_t>::max();
                } else {
                    processed += partial;
                }
                if (processed > total_units) processed = total_units;

                auto mapped = source;
                mapped.phase = OperationPhase::Extracting;
                mapped.processed_bytes = processed;
                mapped.total_bytes = total_units;
                mapped.fraction = total_units
                    ? static_cast<double>(processed)
                        / static_cast<double>(total_units)
                    : 1.0;
                parent->report(std::move(mapped));
            },
            [parent]() {
                return parent->is_cancelled();
            });
    }

    [[nodiscard]] BackendOptions options(const BackendOptions& base) noexcept {
        auto out = base;
        out.operation = enabled_ ? &context_ : nullptr;
        return out;
    }

private:
    OperationContext context_{};
    bool enabled_{false};
};

} // namespace kephir2::aur2
