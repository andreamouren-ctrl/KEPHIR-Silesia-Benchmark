#include "kephir2/analyzer.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace kephir2 {
namespace {

bool is_printable(std::uint8_t b) noexcept {
    return b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127);
}

bool is_letter_or_space(std::uint8_t b) noexcept {
    return b == 32 || (b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z');
}

bool in_bytes(std::uint8_t b, std::string_view chars) noexcept {
    return chars.find(static_cast<char>(b)) != std::string_view::npos;
}

ContentClass classify_metrics(
    std::uint64_t original_bytes,
    std::span<const std::uint8_t> sample,
    const SampleMetrics& m) {

    if (original_bytes == 0) {
        return ContentClass::Empty;
    }

    if (original_bytes <= 192) {
        return m.printable_fraction >= 0.85
            ? ContentClass::TinyText
            : ContentClass::TinyBinary;
    }

    if (m.printable_fraction >= 0.88) {
        constexpr std::string_view b64 =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n";

        std::size_t base64_count = 0;
        std::size_t code_punctuation = 0;
        std::size_t config_punctuation = 0;
        std::size_t newlines = 0;

        for (const auto b : sample) {
            base64_count += in_bytes(b, b64) ? 1u : 0u;
            code_punctuation += in_bytes(b, "(){}[];=_<>") ? 1u : 0u;
            config_punctuation += in_bytes(b, ":-\"'") ? 1u : 0u;
            newlines += b == 10 ? 1u : 0u;
        }

        const double n = static_cast<double>(sample.size());
        const double base64_fraction = n ? static_cast<double>(base64_count) / n : 0.0;
        if (base64_fraction >= 0.985 && m.entropy >= 4.0 && m.entropy <= 6.5) {
            return ContentClass::EncodedText;
        }

        const double code_fraction = n ? static_cast<double>(code_punctuation) / n : 0.0;
        const double config_fraction = n ? static_cast<double>(config_punctuation) / n : 0.0;
        const double newline_fraction = n ? static_cast<double>(newlines) / n : 0.0;

        if (code_fraction >= 0.028) {
            return ContentClass::TextCode;
        }
        if (config_fraction >= 0.035 && newline_fraction >= 0.010) {
            return ContentClass::TextConfig;
        }
        if (m.letters_space_fraction >= 0.63) {
            return ContentClass::TextProse;
        }
        return ContentClass::TextGeneric;
    }

    if (m.zero_fraction >= 0.08) {
        return ContentClass::BinaryZero;
    }
    if (m.entropy < 5.5) {
        return ContentClass::BinaryLow;
    }
    if (m.entropy < 7.3) {
        return ContentClass::BinaryMid;
    }
    return ContentClass::BinaryHigh;
}

SampleMetrics compute_metrics(
    std::uint64_t original_bytes,
    std::span<const std::uint8_t> sample) {

    SampleMetrics m{};
    m.original_bytes = original_bytes;
    m.sampled_bytes = sample.size();

    if (sample.empty()) {
        return m;
    }

    std::size_t printable = 0;
    std::size_t letters_space = 0;
    std::size_t zeros = 0;
    for (const auto b : sample) {
        printable += is_printable(b) ? 1u : 0u;
        letters_space += is_letter_or_space(b) ? 1u : 0u;
        zeros += b == 0 ? 1u : 0u;
    }

    const double n = static_cast<double>(sample.size());
    m.printable_fraction = static_cast<double>(printable) / n;
    m.letters_space_fraction = static_cast<double>(letters_space) / n;
    m.zero_fraction = static_cast<double>(zeros) / n;

    std::array<std::uint64_t, 256> counts{};
    for (const auto b : sample) {
        ++counts[b];
    }

    double h = 0.0;
    for (const auto count : counts) {
        if (!count) {
            continue;
        }
        const double p = static_cast<double>(count) / n;
        h -= p * std::log2(p);
    }
    m.entropy = h;
    return m;
}

std::vector<std::filesystem::path> collect_files(const std::filesystem::path& root) {
    std::vector<std::filesystem::path> out;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        std::error_code ec;
        if (entry.is_regular_file(ec) && !entry.is_symlink(ec)) {
            out.push_back(entry.path());
        }
    }

    std::sort(out.begin(), out.end(), [&root](const auto& a, const auto& b) {
        return a.lexically_relative(root).generic_string()
            < b.lexically_relative(root).generic_string();
    });
    return out;
}

} // namespace

std::string_view to_string(ContentClass value) noexcept {
    switch (value) {
    case ContentClass::Empty: return "empty";
    case ContentClass::TinyText: return "tiny-text";
    case ContentClass::TinyBinary: return "tiny-binary";
    case ContentClass::EncodedText: return "encoded-text";
    case ContentClass::TextCode: return "text-code";
    case ContentClass::TextConfig: return "text-config";
    case ContentClass::TextProse: return "text-prose";
    case ContentClass::TextGeneric: return "text-generic";
    case ContentClass::BinaryZero: return "binary-zero";
    case ContentClass::BinaryLow: return "binary-low";
    case ContentClass::BinaryMid: return "binary-mid";
    case ContentClass::BinaryHigh: return "binary-high";
    }
    return "unknown";
}

double ContentAnalyzer::entropy(std::span<const std::uint8_t> sample) {
    return compute_metrics(sample.size(), sample).entropy;
}

std::vector<std::uint8_t> ContentAnalyzer::python_compatible_stride_sample(
    std::span<const std::uint8_t> data,
    std::size_t target_samples) {

    if (data.empty()) {
        return {};
    }
    const std::size_t target = std::max<std::size_t>(1, target_samples);
    const std::size_t step = std::max<std::size_t>(1, data.size() / target);

    std::vector<std::uint8_t> out;
    out.reserve((data.size() + step - 1) / step);
    for (std::size_t i = 0; i < data.size(); i += step) {
        out.push_back(data[i]);
    }
    return out;
}

FileAnalysis ContentAnalyzer::analyze_bytes(std::span<const std::uint8_t> data) const {
    constexpr std::size_t kClassifierSamples = 8192;
    const auto sample = python_compatible_stride_sample(data, kClassifierSamples);
    auto metrics = compute_metrics(data.size(), sample);
    return {classify_metrics(data.size(), sample, metrics), metrics};
}

FileAnalysis ContentAnalyzer::analyze_file(const std::filesystem::path& path) const {
    const auto size = std::filesystem::file_size(path);
    if (size == 0) {
        return {ContentClass::Empty, SampleMetrics{}};
    }

    constexpr std::uint64_t kTargetSamples = 8192;
    const std::uint64_t step = std::max<std::uint64_t>(1, size / kTargetSamples);

    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("unable to open file for KEPHIR content analysis");
    }

    std::vector<std::uint8_t> sample;
    sample.reserve(static_cast<std::size_t>((size + step - 1) / step));

    for (std::uint64_t pos = 0; pos < size; pos += step) {
        in.seekg(static_cast<std::streamoff>(pos), std::ios::beg);
        char ch = 0;
        in.read(&ch, 1);
        if (!in) {
            throw std::runtime_error("unable to sample file for KEPHIR content analysis");
        }
        sample.push_back(static_cast<std::uint8_t>(static_cast<unsigned char>(ch)));
    }

    auto metrics = compute_metrics(size, sample);
    return {classify_metrics(size, sample, metrics), metrics};
}

ArchiveFeatures ContentAnalyzer::analyze_directory(
    const std::filesystem::path& root,
    const AnalyzerOptions& options) const {

    const auto paths = collect_files(root);

    ArchiveFeatures out{};
    out.file_count = paths.size();
    if (paths.empty()) {
        out.sampled_content_groups = 0;
        out.sampled_dominant_file_fraction = 0.0;
        out.sampled_dominant_byte_fraction = 0.0;
        return out;
    }

    std::vector<std::uint64_t> sizes;
    sizes.reserve(paths.size());

    std::array<std::uint64_t, 12> class_files{};
    std::array<std::uint64_t, 12> class_bytes{};

    std::array<std::uint64_t, 256> aggregate_counts{};
    std::uint64_t aggregate_sampled = 0;
    std::uint64_t aggregate_printable = 0;
    std::uint64_t aggregate_zero = 0;

    std::uint64_t small_files = 0;

    for (const auto& path : paths) {
        const auto size = std::filesystem::file_size(path);
        sizes.push_back(size);
        out.logical_bytes += size;
        small_files += size <= options.small_file_threshold ? 1u : 0u;

        const auto analysis = analyze_file(path);
        const auto ci = static_cast<std::size_t>(analysis.content_class);
        ++class_files[ci];
        class_bytes[ci] += size;

        // Directory aggregate signals are intentionally capped. Diversity
        // counts remain exact per-file decisions; aggregate byte metrics stop
        // once the directory sample budget is exhausted.
        if (aggregate_sampled < options.directory_sample_budget) {
            std::ifstream in(path, std::ios::binary);
            if (!in) {
                throw std::runtime_error("unable to open file for directory sampling");
            }

            const std::uint64_t remaining =
                options.directory_sample_budget - aggregate_sampled;
            const std::uint64_t want = std::min<std::uint64_t>(remaining, std::min<std::uint64_t>(size, 8192));
            if (want != 0) {
                const std::uint64_t step = std::max<std::uint64_t>(1, size / want);
                std::uint64_t taken = 0;
                for (std::uint64_t pos = 0; pos < size && taken < want; pos += step) {
                    in.seekg(static_cast<std::streamoff>(pos), std::ios::beg);
                    char ch = 0;
                    in.read(&ch, 1);
                    if (!in) {
                        break;
                    }
                    const auto b = static_cast<std::uint8_t>(static_cast<unsigned char>(ch));
                    ++aggregate_counts[b];
                    aggregate_printable += is_printable(b) ? 1u : 0u;
                    aggregate_zero += b == 0 ? 1u : 0u;
                    ++aggregate_sampled;
                    ++taken;
                }
            }
        }
    }

    const double file_count = static_cast<double>(out.file_count);
    out.average_file_bytes = static_cast<double>(out.logical_bytes) / file_count;
    out.small_file_fraction = static_cast<double>(small_files) / file_count;

    std::sort(sizes.begin(), sizes.end());
    if (sizes.size() % 2 == 1) {
        out.median_file_bytes = static_cast<double>(sizes[sizes.size() / 2]);
    } else {
        const auto a = sizes[sizes.size() / 2 - 1];
        const auto b = sizes[sizes.size() / 2];
        out.median_file_bytes = (static_cast<double>(a) + static_cast<double>(b)) / 2.0;
    }

    std::uint64_t dominant_files = 0;
    std::uint64_t dominant_bytes = 0;
    std::uint64_t repeatable_bytes = 0;
    std::uint32_t groups = 0;
    std::uint32_t multi_file_groups = 0;
    for (std::size_t i = 0; i < class_files.size(); ++i) {
        if (class_files[i] != 0) {
            ++groups;
        }
        if (class_files[i] >= 2) {
            ++multi_file_groups;
            repeatable_bytes += class_bytes[i];
        }
        dominant_files = std::max(dominant_files, class_files[i]);
        dominant_bytes = std::max(dominant_bytes, class_bytes[i]);
    }

    out.sampled_content_groups = groups;
    out.multi_file_content_groups = multi_file_groups;
    out.sampled_dominant_file_fraction =
        static_cast<double>(dominant_files) / file_count;
    out.sampled_dominant_byte_fraction =
        out.logical_bytes ? static_cast<double>(dominant_bytes) / static_cast<double>(out.logical_bytes) : 0.0;
    out.repeatable_content_byte_fraction =
        out.logical_bytes ? static_cast<double>(repeatable_bytes) / static_cast<double>(out.logical_bytes) : 0.0;

    if (aggregate_sampled != 0) {
        const double n = static_cast<double>(aggregate_sampled);
        out.sampled_printable_fraction = static_cast<double>(aggregate_printable) / n;
        out.sampled_zero_fraction = static_cast<double>(aggregate_zero) / n;

        double h = 0.0;
        for (const auto count : aggregate_counts) {
            if (!count) {
                continue;
            }
            const double p = static_cast<double>(count) / n;
            h -= p * std::log2(p);
        }
        out.sampled_entropy = h;
    }

    return out;
}

} // namespace kephir2
