#pragma once

#include "kephir2/strategy.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string_view>
#include <vector>

namespace kephir2 {

enum class ContentClass : std::uint8_t {
    Empty,
    TinyText,
    TinyBinary,
    EncodedText,
    TextCode,
    TextConfig,
    TextProse,
    TextGeneric,
    BinaryZero,
    BinaryLow,
    BinaryMid,
    BinaryHigh
};

[[nodiscard]] std::string_view to_string(ContentClass value) noexcept;

struct SampleMetrics {
    std::uint64_t original_bytes{0};
    std::uint64_t sampled_bytes{0};
    double entropy{0.0};
    double printable_fraction{0.0};
    double letters_space_fraction{0.0};
    double zero_fraction{0.0};
};

struct FileAnalysis {
    ContentClass content_class{ContentClass::Empty};
    SampleMetrics metrics{};
};

struct AnalyzerOptions {
    // Python KEPHIR 1.0 classifies at most roughly 8192 strided bytes per file.
    std::size_t classifier_target_samples{8192};

    // Directory-level statistics use at most this many sampled payload bytes.
    // Metadata statistics (counts/sizes) are exact and do not consume this budget.
    std::size_t directory_sample_budget{2u * 1024u * 1024u};

    // KEPHIR product definition for a "small" file.
    std::uint64_t small_file_threshold{64u * 1024u};
};

class ContentAnalyzer {
public:
    [[nodiscard]] FileAnalysis analyze_bytes(std::span<const std::uint8_t> data) const;
    [[nodiscard]] FileAnalysis analyze_file(const std::filesystem::path& path) const;

    // Deterministic directory analysis. Files are ordered lexicographically by
    // normalized relative path. The returned ArchiveFeatures can be consumed
    // directly by GlobalRouter.
    [[nodiscard]] ArchiveFeatures analyze_directory(
        const std::filesystem::path& root,
        const AnalyzerOptions& options = {}) const;

private:
    [[nodiscard]] static double entropy(std::span<const std::uint8_t> sample);
    [[nodiscard]] static std::vector<std::uint8_t> python_compatible_stride_sample(
        std::span<const std::uint8_t> data,
        std::size_t target_samples);
};

} // namespace kephir2
