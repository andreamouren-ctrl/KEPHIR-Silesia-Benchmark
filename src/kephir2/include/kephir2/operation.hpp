#pragma once

#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>

namespace kephir2 {

enum class OperationPhase : std::uint8_t {
    Idle,
    Scanning,
    Analyzing,
    Planning,
    Packing,
    Compressing,
    Writing,
    Verifying,
    Extracting,
    Done
};

struct OperationProgress {
    OperationPhase phase{OperationPhase::Idle};
    double fraction{0.0};
    std::uint64_t processed_bytes{0};
    std::uint64_t total_bytes{0};
    std::string current_path{};
};

class OperationCancelled final : public std::runtime_error {
public:
    OperationCancelled()
        : std::runtime_error("KEPHIR operation cancelled") {}
};

class OperationContext {
public:
    using ProgressCallback = std::function<void(const OperationProgress&)>;
    using CancelCallback = std::function<bool()>;

    OperationContext() = default;

    OperationContext(
        ProgressCallback progress,
        CancelCallback cancel)
        : progress_(std::move(progress)),
          cancel_(std::move(cancel)) {}

    [[nodiscard]] bool is_cancelled() const {
        return cancel_ && cancel_();
    }

    void throw_if_cancelled() const {
        if (is_cancelled()) {
            throw OperationCancelled{};
        }
    }

    void report(OperationProgress progress) const {
        throw_if_cancelled();
        if (progress.fraction < 0.0) progress.fraction = 0.0;
        if (progress.fraction > 1.0) progress.fraction = 1.0;
        if (progress_) {
            progress_(progress);
        }
    }

private:
    ProgressCallback progress_{};
    CancelCallback cancel_{};
};

} // namespace kephir2
