#include "kephir2/aur2_progress.hpp"

#include <algorithm>
#include <limits>

namespace kephir2::aur2 {
namespace {

std::uint64_t scaled_processed(
    std::uint64_t completed,
    std::uint64_t stream_units,
    double fraction) noexcept {

    const double local = std::clamp(fraction, 0.0, 1.0);
    if (local <= 0.0) return completed;
    if (local >= 1.0) {
        return stream_units > std::numeric_limits<std::uint64_t>::max() - completed
            ? std::numeric_limits<std::uint64_t>::max()
            : completed + stream_units;
    }

    const long double scaled =
        static_cast<long double>(stream_units) * static_cast<long double>(local);
    const auto partial = static_cast<std::uint64_t>(scaled);
    return partial > std::numeric_limits<std::uint64_t>::max() - completed
        ? std::numeric_limits<std::uint64_t>::max()
        : completed + partial;
}

} // namespace

StreamProgressAdapter::StreamProgressAdapter(
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

            auto mapped = source;
            mapped.phase = OperationPhase::Extracting;
            mapped.processed_bytes = scaled_processed(
                completed_units,
                stream_units,
                source.fraction);
            if (mapped.processed_bytes > total_units) {
                mapped.processed_bytes = total_units;
            }
            mapped.total_bytes = total_units;
            mapped.fraction = total_units
                ? static_cast<double>(mapped.processed_bytes)
                    / static_cast<double>(total_units)
                : 1.0;
            parent->report(std::move(mapped));
        },
        [parent]() {
            return parent->is_cancelled();
        });
}

BackendOptions StreamProgressAdapter::options(
    const BackendOptions& base) noexcept {

    auto out = base;
    out.operation = enabled_ ? &context_ : nullptr;
    return out;
}

} // namespace kephir2::aur2
