#include "kephir2/native_k75.hpp"

#include "kephir2/native37_blob.hpp"
#include "kephir2/factory_grain_v1.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <future>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

namespace kephir2 {
namespace {

constexpr std::size_t kParentBytes = 512u * 1024u;
constexpr std::array<std::string_view, 32> kTextTokens{
    " the "," and ","ing","tion"," of "," to "," in "," that ",
    " is "," for ","ed ","er ","re ","en ","on ","at ",
    "\\n","</","/>","http","www.","=\"","<!--","-->",
    "data","this","with","from","have","not "," as "," by "
};

struct EncodedEntry {
    std::uint8_t mode{0};
    std::uint32_t raw_size{0};
    std::vector<std::uint8_t> compressed;
};

void put_u32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    for (unsigned k = 0; k < 4; ++k)
        out.push_back(static_cast<std::uint8_t>(value >> (8u * k)));
}

void put_u64(std::vector<std::uint8_t>& out, std::uint64_t value) {
    for (unsigned k = 0; k < 8; ++k)
        out.push_back(static_cast<std::uint8_t>(value >> (8u * k)));
}

std::uint32_t get_u32(std::span<const std::uint8_t> data, std::size_t& pos) {
    if (data.size() - pos < 4) throw std::runtime_error("truncated K75 u32");
    std::uint32_t value = 0;
    for (unsigned k = 0; k < 4; ++k)
        value |= static_cast<std::uint32_t>(data[pos++]) << (8u * k);
    return value;
}

std::uint64_t get_u64(std::span<const std::uint8_t> data, std::size_t& pos) {
    if (data.size() - pos < 8) throw std::runtime_error("truncated K75 u64");
    std::uint64_t value = 0;
    for (unsigned k = 0; k < 8; ++k)
        value |= static_cast<std::uint64_t>(data[pos++]) << (8u * k);
    return value;
}

double entropy_values(std::span<const std::uint8_t> values) {
    if (values.empty()) return 0.0;
    std::array<std::uint64_t, 256> counts{};
    for (const auto b : values) ++counts[b];
    const double n = static_cast<double>(values.size());
    double h = 0.0;
    for (const auto count : counts) {
        if (!count) continue;
        const double p = static_cast<double>(count) / n;
        h -= p * std::log2(p);
    }
    return h;
}

double sample_entropy(
    std::span<const std::uint8_t> input,
    std::size_t step = 32) {

    if (input.empty()) return 0.0;
    std::vector<std::uint8_t> sample;
    sample.reserve((input.size() + step - 1) / step);
    for (std::size_t i = 0; i < input.size(); i += step)
        sample.push_back(input[i]);
    return entropy_values(sample);
}

double residual_entropy(
    std::span<const std::uint8_t> input,
    std::size_t lag,
    std::size_t step = 32) {

    if (input.size() <= lag) return 99.0;
    std::vector<std::uint8_t> values;
    values.reserve((input.size() - lag + step - 1) / step);
    for (std::size_t i = lag; i < input.size(); i += step)
        values.push_back(static_cast<std::uint8_t>(input[i] - input[i - lag]));
    return entropy_values(values);
}

bool is_text_like(std::span<const std::uint8_t> input) {
    if (input.empty()) return false;
    std::uint64_t printable = 0, letters_space = 0, n = 0;
    for (std::size_t i = 0; i < input.size(); i += 32) {
        const auto b = input[i];
        printable += (b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127)) ? 1u : 0u;
        letters_space += (b == 32 || (b >= 65 && b <= 90) || (b >= 97 && b <= 122)) ? 1u : 0u;
        ++n;
    }
    return n
        && static_cast<double>(printable) / n >= 0.88
        && static_cast<double>(letters_space) / n >= 0.58;
}

std::vector<std::uint8_t> delta_lag(
    std::span<const std::uint8_t> input,
    std::size_t lag) {

    std::vector<std::uint8_t> out(input.size());
    for (std::size_t i = 0; i < input.size(); ++i)
        out[i] = i < lag ? input[i]
            : static_cast<std::uint8_t>(input[i] - input[i - lag]);
    return out;
}

std::vector<std::uint8_t> inv_delta(
    std::span<const std::uint8_t> input,
    std::size_t lag) {

    std::vector<std::uint8_t> out(input.size());
    for (std::size_t i = 0; i < input.size(); ++i)
        out[i] = i < lag ? input[i]
            : static_cast<std::uint8_t>(input[i] + out[i - lag]);
    return out;
}

std::vector<std::uint8_t> transpose(
    std::span<const std::uint8_t> input,
    std::size_t width) {

    const auto rows = input.size() / width;
    const auto main = rows * width;
    std::vector<std::uint8_t> out;
    out.reserve(input.size());
    for (std::size_t c = 0; c < width; ++c)
        for (std::size_t i = c; i < main; i += width)
            out.push_back(input[i]);
    out.insert(out.end(), input.begin() + static_cast<std::ptrdiff_t>(main), input.end());
    return out;
}

std::vector<std::uint8_t> inv_transpose(
    std::span<const std::uint8_t> input,
    std::size_t width,
    std::size_t raw_length) {

    if (input.size() != raw_length)
        throw std::runtime_error("transposed payload length mismatch");
    const auto rows = raw_length / width;
    const auto main = rows * width;
    std::vector<std::uint8_t> out(raw_length);
    std::size_t k = 0;
    for (std::size_t c = 0; c < width; ++c)
        for (std::size_t r = 0; r < rows; ++r)
            out[r * width + c] = input[k++];
    for (std::size_t i = main; i < raw_length; ++i)
        out[i] = input[k++];
    return out;
}

std::vector<std::uint8_t> word_xor(
    std::span<const std::uint8_t> input,
    std::size_t width = 2) {

    const auto main = (input.size() / width) * width;
    std::vector<std::uint8_t> out(input.size());
    std::uint64_t previous = 0;
    for (std::size_t i = 0; i < main; i += width) {
        std::uint64_t value = 0;
        for (std::size_t k = 0; k < width; ++k)
            value |= static_cast<std::uint64_t>(input[i + k]) << (8u * k);
        const auto encoded = i == 0 ? value : (value ^ previous);
        for (std::size_t k = 0; k < width; ++k)
            out[i + k] = static_cast<std::uint8_t>(encoded >> (8u * k));
        previous = value;
    }
    std::copy(input.begin() + static_cast<std::ptrdiff_t>(main), input.end(),
              out.begin() + static_cast<std::ptrdiff_t>(main));
    return out;
}

std::vector<std::uint8_t> inv_word_xor(
    std::span<const std::uint8_t> input,
    std::size_t width = 2) {

    const auto main = (input.size() / width) * width;
    std::vector<std::uint8_t> out(input.size());
    std::uint64_t previous = 0;
    for (std::size_t i = 0; i < main; i += width) {
        std::uint64_t encoded = 0;
        for (std::size_t k = 0; k < width; ++k)
            encoded |= static_cast<std::uint64_t>(input[i + k]) << (8u * k);
        const auto value = i == 0 ? encoded : (encoded ^ previous);
        for (std::size_t k = 0; k < width; ++k)
            out[i + k] = static_cast<std::uint8_t>(value >> (8u * k));
        previous = value;
    }
    std::copy(input.begin() + static_cast<std::ptrdiff_t>(main), input.end(),
              out.begin() + static_cast<std::ptrdiff_t>(main));
    return out;
}

std::vector<std::uint8_t> text_tokenize(std::span<const std::uint8_t> input) {
    std::vector<std::size_t> order(kTextTokens.size());
    for (std::size_t i = 0; i < order.size(); ++i) order[i] = i;
    std::stable_sort(order.begin(), order.end(), [](std::size_t a, std::size_t b) {
        return kTextTokens[a].size() > kTextTokens[b].size();
    });

    std::vector<std::uint8_t> out;
    std::size_t i = 0;
    while (i < input.size()) {
        bool matched = false;
        for (const auto token_index : order) {
            const auto token = kTextTokens[token_index];
            if (token.empty()
                || static_cast<std::uint8_t>(token.front()) != input[i]
                || token.size() > input.size() - i) continue;

            bool equal = true;
            for (std::size_t k = 0; k < token.size(); ++k) {
                if (input[i + k] != static_cast<std::uint8_t>(token[k])) {
                    equal = false;
                    break;
                }
            }
            if (!equal) continue;

            out.push_back(255);
            out.push_back(static_cast<std::uint8_t>(token_index + 1));
            i += token.size();
            matched = true;
            break;
        }
        if (matched) continue;
        if (input[i] == 255) {
            out.push_back(255);
            out.push_back(0);
        } else {
            out.push_back(input[i]);
        }
        ++i;
    }
    return out;
}

std::vector<std::uint8_t> text_detokenize(std::span<const std::uint8_t> input) {
    std::vector<std::uint8_t> out;
    std::size_t i = 0;
    while (i < input.size()) {
        const auto b = input[i++];
        if (b != 255) {
            out.push_back(b);
            continue;
        }
        if (i >= input.size())
            throw std::runtime_error("truncated text token stream");
        const auto token_id = input[i++];
        if (token_id == 0) {
            out.push_back(255);
        } else {
            if (token_id > kTextTokens.size())
                throw std::runtime_error("invalid text token id");
            const auto token = kTextTokens[token_id - 1];
            for (const auto ch : token)
                out.push_back(static_cast<std::uint8_t>(ch));
        }
    }
    return out;
}

std::string wx_coarse_bucket(std::span<const std::uint8_t> input) {
    if (input.empty()) return "empty";

    std::vector<std::uint8_t> sample;
    sample.reserve((input.size() + 63u) / 64u);

    std::uint64_t zero = 0;
    std::uint64_t printable = 0;

    for (std::size_t i = 0; i < input.size(); i += 64u) {
        const auto b = input[i];
        sample.push_back(b);
        zero += b == 0 ? 1u : 0u;
        printable +=
            (b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127))
            ? 1u : 0u;
    }

    const double h = entropy_values(sample);
    const double zero_fraction =
        static_cast<double>(zero) / sample.size();
    const double printable_fraction =
        static_cast<double>(printable) / sample.size();

    const int sb =
        input.size() <= 128u * 1024u ? 0
        : (input.size() <= 256u * 1024u ? 1 : 2);
    const auto hb = std::min(7, static_cast<int>(h));
    const auto zb = std::min(4, static_cast<int>(zero_fraction * 10.0));
    const auto pb = std::min(4, static_cast<int>(printable_fraction * 5.0));

    return "wx:s" + std::to_string(sb)
        + ":h" + std::to_string(hb)
        + ":z" + std::to_string(zb)
        + ":p" + std::to_string(pb);
}

std::string wx_feature_bucket(
    std::span<const std::uint8_t> input,
    const std::string& coarse) {

    if (input.empty()) return coarse;

    const double r2 = residual_entropy(input, 2, 64);
    const double r4 = residual_entropy(input, 4, 64);

    const auto q = std::max<std::size_t>(1, input.size() / 4);
    std::vector<double> hs;
    for (std::size_t i = 0; i < input.size(); i += q) {
        const auto bytes = std::min(q, input.size() - i);
        hs.push_back(sample_entropy(input.subspan(i, bytes), 64));
    }

    const auto [min_it, max_it] =
        std::minmax_element(hs.begin(), hs.end());
    const double spread =
        hs.empty() ? 0.0 : (*max_it - *min_it);

    const auto r2b = std::min(15, static_cast<int>(r2 * 2.0));
    const auto r4b = std::min(15, static_cast<int>(r4 * 2.0));
    const auto spb = std::min(7, static_cast<int>(spread * 4.0));

    return coarse
        + ":r2" + std::to_string(r2b)
        + ":r4" + std::to_string(r4b)
        + ":sp" + std::to_string(spb);
}

bool should_probe_word_xor(std::span<const std::uint8_t> input) {
    if (input.empty() || is_text_like(input)) return false;

    const auto coarse = wx_coarse_bucket(input);
    if (coarse != "wx:s0:h3:z0:p4"
        && coarse != "wx:s2:h6:z1:p1") {
        return false;
    }

    const auto fine = wx_feature_bucket(input, coarse);
    return fine == "wx:s0:h3:z0:p4:r210:r411:sp3"
        || fine == "wx:s2:h6:z1:p1:r213:r413:sp4";
}

std::uint8_t choose_mode(std::span<const std::uint8_t> input) {
    struct Candidate { double entropy; std::uint8_t mode; };
    const double raw_h = sample_entropy(input);
    const std::array<Candidate, 5> candidates{{
        {raw_h, 0},
        {residual_entropy(input, 2), 4},
        {residual_entropy(input, 4), 1},
        {residual_entropy(input, 16), 5},
        {residual_entropy(input, 1024), 2},
    }};
    const auto best = std::min_element(
        candidates.begin(), candidates.end(),
        [](const auto& a, const auto& b) { return a.entropy < b.entropy; });
    if (best->mode != 0 && raw_h - best->entropy < 0.10) return 0;
    return best->mode;
}

std::size_t choose_grain(std::span<const std::uint8_t> parent) {
    if (parent.size() <= 128u * 1024u) return parent.size();

    std::vector<double> parts;
    constexpr std::size_t q = 128u * 1024u;
    for (std::size_t offset = 0; offset < parent.size(); offset += q) {
        const auto bytes = std::min(q, parent.size() - offset);
        parts.push_back(sample_entropy(parent.subspan(offset, bytes), 32));
    }

    const auto [min_it, max_it] = std::minmax_element(parts.begin(), parts.end());
    const double spread = parts.empty() ? 0.0 : (*max_it - *min_it);

    if (parent.size() > 256u * 1024u && spread >= 0.75) return 128u * 1024u;
    if (parent.size() > 256u * 1024u && spread >= 0.40) return 256u * 1024u;
    return parent.size();
}

std::string grain_feature_bucket(std::span<const std::uint8_t> parent) {
    if (parent.empty()) return "empty";

    std::vector<std::uint8_t> sample;
    sample.reserve((parent.size() + 63u) / 64u);

    std::uint64_t zero = 0;
    std::uint64_t printable = 0;

    for (std::size_t i = 0; i < parent.size(); i += 64u) {
        const auto b = parent[i];
        sample.push_back(b);
        zero += b == 0 ? 1u : 0u;
        printable +=
            (b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127))
            ? 1u : 0u;
    }

    const double h = entropy_values(sample);
    const double zero_fraction =
        static_cast<double>(zero) / sample.size();
    const double printable_fraction =
        static_cast<double>(printable) / sample.size();

    std::vector<double> parts;
    constexpr std::size_t q = 128u * 1024u;
    for (std::size_t offset = 0; offset < parent.size(); offset += q) {
        const auto bytes = std::min(q, parent.size() - offset);
        parts.push_back(sample_entropy(parent.subspan(offset, bytes), 32));
    }

    const auto [min_it, max_it] =
        std::minmax_element(parts.begin(), parts.end());
    const double spread =
        parts.empty() ? 0.0 : (*max_it - *min_it);

    const auto hb = std::min(7, static_cast<int>(h));
    const auto zb = std::min(4, static_cast<int>(zero_fraction * 10.0));
    const auto pb = std::min(4, static_cast<int>(printable_fraction * 5.0));
    const auto sp = std::min(7, static_cast<int>(spread * 4.0));
    const int lb =
        parent.size() < 256u * 1024u ? 0
        : (parent.size() < kParentBytes ? 1 : 2);

    return "l" + std::to_string(lb)
        + ":h" + std::to_string(hb)
        + ":z" + std::to_string(zb)
        + ":p" + std::to_string(pb)
        + ":s" + std::to_string(sp);
}

bool valid_grain_candidate(
    std::size_t parent_size,
    std::size_t grain) noexcept {

    if (grain == parent_size) return true;
    if (parent_size > 128u * 1024u && grain == 128u * 1024u) return true;
    if (parent_size > 256u * 1024u && grain == 256u * 1024u) return true;
    return false;
}

std::size_t distribution_drift_grain(
    std::span<const std::uint8_t> parent,
    std::string_view coarse_key) {

    // EXP-106: only refine the high-entropy / low-entropy-spread bucket for
    // which EXP-104 proved that coarse entropy is ambiguous. Existing trusted
    // factory rules retain priority.
    if (parent.size() != kParentBytes
        || coarse_key != "l2:h7:z0:p1:s0") {
        return 0;
    }

    constexpr std::size_t kQuarter = 128u * 1024u;
    std::array<std::array<std::uint32_t, 256>, 4> counts{};
    std::array<std::uint32_t, 4> printable{};

    for (std::size_t q = 0; q < 4; ++q) {
        const auto part = parent.subspan(q * kQuarter, kQuarter);
        for (const auto b : part) {
            ++counts[q][b];
            printable[q] +=
                (b == 9 || b == 10 || b == 13 || (b >= 32 && b < 127))
                ? 1u : 0u;
        }
    }

    double tv_max = 0.0;
    for (std::size_t a = 0; a < 4; ++a) {
        for (std::size_t b = a + 1; b < 4; ++b) {
            std::uint64_t l1 = 0;
            for (std::size_t symbol = 0; symbol < 256; ++symbol) {
                const auto av = counts[a][symbol];
                const auto bv = counts[b][symbol];
                l1 += av >= bv ? av - bv : bv - av;
            }
            const double tv =
                static_cast<double>(l1)
                / (2.0 * static_cast<double>(kQuarter));
            tv_max = std::max(tv_max, tv);
        }
    }

    const auto [pmin, pmax] =
        std::minmax_element(printable.begin(), printable.end());
    const double printable_range =
        static_cast<double>(*pmax - *pmin)
        / static_cast<double>(kQuarter);

    // EXP-105 observed that genuine local distribution drift with stable
    // printable fraction separates the valuable mozilla/x-ray splits from
    // synthetic random/incompressible parents. The lower-drift case benefits
    // from 128 KiB; stronger drift benefits from 256 KiB.
    if (tv_max > 0.04 && printable_range < 0.01) {
        return tv_max < 0.07
            ? 128u * 1024u
            : 256u * 1024u;
    }

    return 0;
}

std::size_t trusted_factory_grain(
    std::span<const std::uint8_t> parent) {

    const auto baseline = choose_grain(parent);
    const auto key = grain_feature_bucket(parent);

    double best_score = -1.0;
    std::uint32_t best_trials = 0;
    std::size_t best_grain = baseline;

    for (const auto& rule : factory_grain::kRules) {
        if (rule.key != key) continue;
        if (!valid_grain_candidate(parent.size(), rule.grain)) continue;

        const double trials = static_cast<double>(rule.trials);
        const double win_rate =
            static_cast<double>(rule.wins) / trials;
        const double average_gain =
            static_cast<double>(rule.gain) / trials;

        const double score = average_gain * win_rate;
        if (score > best_score
            || (score == best_score && rule.trials > best_trials)) {
            best_score = score;
            best_trials = rule.trials;
            best_grain = rule.grain;
        }
    }

    if (best_score < 0.0) {
        const auto drift_grain =
            distribution_drift_grain(parent, key);
        if (drift_grain != 0
            && valid_grain_candidate(parent.size(), drift_grain)) {
            return drift_grain;
        }
    }

    return best_grain;
}

std::vector<std::uint8_t> transform(
    std::span<const std::uint8_t> input,
    std::uint8_t mode) {

    switch (mode) {
    case 0: return {input.begin(), input.end()};
    case 1: return transpose(delta_lag(input, 4), 4);
    case 2: return transpose(delta_lag(input, 1024), 1024);
    case 3: return transpose(word_xor(input, 2), 2);
    case 4: return transpose(delta_lag(input, 2), 2);
    case 5: return transpose(delta_lag(input, 16), 16);
    case 6: return text_tokenize(input);
    default: throw std::runtime_error("invalid K75 transform mode");
    }
}

std::vector<std::uint8_t> inverse(
    std::span<const std::uint8_t> input,
    std::uint8_t mode,
    std::size_t raw_length) {

    switch (mode) {
    case 0: return {input.begin(), input.end()};
    case 1: return inv_delta(inv_transpose(input, 4, raw_length), 4);
    case 2: return inv_delta(inv_transpose(input, 1024, raw_length), 1024);
    case 3: return inv_word_xor(inv_transpose(input, 2, raw_length), 2);
    case 4: return inv_delta(inv_transpose(input, 2, raw_length), 2);
    case 5: return inv_delta(inv_transpose(input, 16, raw_length), 16);
    case 6: return text_detokenize(input);
    default: throw std::runtime_error("invalid K75 transform mode");
    }
}

EncodedEntry encode_entry_impl(
    std::span<const std::uint8_t> raw,
    bool allow_word_xor,
    std::size_t inner_chunk_bytes) {

    if (raw.size() > std::numeric_limits<std::uint32_t>::max())
        throw std::runtime_error("K75 grain too large");

    std::uint8_t mode = choose_mode(raw);
    auto compressed = native37::encode_aur2_blob(transform(raw, mode), inner_chunk_bytes);

    if (mode != 0) {
        auto baseline = native37::encode_aur2_blob(raw, inner_chunk_bytes);
        if (baseline.size() <= compressed.size()) {
            mode = 0;
            compressed = std::move(baseline);
        }
    }

    if (allow_word_xor && mode == 0 && should_probe_word_xor(raw)) {
        auto wx_compressed =
            native37::encode_aur2_blob(transform(raw, 3), inner_chunk_bytes);
        if (wx_compressed.size() < compressed.size()) {
            mode = 3;
            compressed = std::move(wx_compressed);
        }
    }

    if (is_text_like(raw)) {
        auto tokenized = text_tokenize(raw);
        if (tokenized.size() + 16 <
            static_cast<std::size_t>(
                static_cast<double>(raw.size()) * 0.99)) {
            auto token_compressed =
                native37::encode_aur2_blob(tokenized, inner_chunk_bytes);
            if (token_compressed.size() < compressed.size()) {
                mode = 6;
                compressed = std::move(token_compressed);
            }
        }
    }

    return {
        mode,
        static_cast<std::uint32_t>(raw.size()),
        std::move(compressed)
    };
}

EncodedEntry encode_entry(
    std::span<const std::uint8_t> raw,
    std::size_t inner_chunk_bytes) {

    return encode_entry_impl(raw, true, inner_chunk_bytes);
}

bool should_exact_grain_probe(std::string_view key) noexcept {
    // EXP-106: the high-frequency h7/s0 family is now handled by the cheap
    // distribution-drift gate. Keep exact probing only for the two rare
    // ambiguous families where the cheap features are not yet sufficient.
    return key == "l2:h5:z2:p1:s6"
        || key == "l2:h5:z1:p3:s2";
}

std::size_t measure_grain_exact_native(
    std::span<const std::uint8_t> parent,
    std::size_t grain,
    std::size_t inner_chunk_bytes) {

    std::size_t total = 0;
    for (std::size_t offset = 0; offset < parent.size(); offset += grain) {
        const auto bytes = std::min(grain, parent.size() - offset);
        const auto encoded =
            encode_entry_impl(
                parent.subspan(offset, bytes),
                false,
                inner_chunk_bytes);

        if (encoded.compressed.size()
            > std::numeric_limits<std::size_t>::max() - total - 9u) {
            throw std::runtime_error("K75 grain probe size overflow");
        }
        total += 9u + encoded.compressed.size();
    }
    return total;
}

std::size_t select_grain(
    std::span<const std::uint8_t> parent,
    std::size_t inner_chunk_bytes,
    bool force_parent_grain) {

    if (force_parent_grain) {
        return parent.size();
    }

    const auto baseline = trusted_factory_grain(parent);
    const auto key = grain_feature_bucket(parent);

    if (!should_exact_grain_probe(key)) {
        return baseline;
    }

    std::array<std::size_t, 3> candidates{
        128u * 1024u,
        256u * 1024u,
        parent.size()
    };

    std::size_t best_grain = baseline;
    std::size_t best_size =
        measure_grain_exact_native(parent, baseline, inner_chunk_bytes);

    for (const auto grain : candidates) {
        if (!valid_grain_candidate(parent.size(), grain)
            || grain == baseline) {
            continue;
        }

        const auto size = measure_grain_exact_native(parent, grain, inner_chunk_bytes);
        if (size < best_size) {
            best_size = size;
            best_grain = grain;
        }
    }

    return best_grain;
}

} // namespace

const char* NativeK75Backend::name() const noexcept {
    return "native-k75-baseline";
}

std::uint32_t NativeK75Backend::format_version() const noexcept {
    return 1u;
}

BackendEncodeResult NativeK75Backend::encode(
    const ByteSource& input,
    const BackendOptions& options) {

    if (options.operation) {
        options.operation->throw_if_cancelled();
        options.operation->report({
            OperationPhase::Compressing,
            0.0,
            0,
            input.size(),
            {}
        });
    }

    std::size_t workers = options.workers;
    if (workers == 0) {
        workers = std::thread::hardware_concurrency();
        if (workers == 0) workers = 1;
    }
    workers = std::clamp<std::size_t>(workers, 1, 16);

    std::vector<EncodedEntry> entries;
    std::vector<std::vector<std::uint8_t>> pending;
    pending.reserve(workers);

    auto flush_pending = [&]() {
        if (pending.empty()) return;

        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        std::vector<std::future<EncodedEntry>> futures;
        futures.reserve(pending.size());

        for (auto& raw : pending) {
            futures.push_back(std::async(
                std::launch::async,
                [raw = std::move(raw)]() mutable {
                    return encode_entry(raw);
                }));
        }

        for (auto& future : futures) {
            entries.push_back(future.get());
        }

        pending.clear();
    };

    std::vector<std::uint8_t> parent(kParentBytes);
    std::uint64_t offset = 0;
    std::uint64_t scheduled_bytes = 0;

    while (offset < input.size()) {
        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        const auto want = static_cast<std::size_t>(
            std::min<std::uint64_t>(
                kParentBytes,
                input.size() - offset));

        const auto got = input.read(
            offset,
            std::span<std::uint8_t>(parent.data(), want));

        if (got != want)
            throw std::runtime_error(
                "short read from K75 byte source");

        const auto parent_span =
            std::span<const std::uint8_t>(parent.data(), got);

        const auto grain = select_grain(parent_span);
        if (!grain)
            throw std::runtime_error("invalid zero K75 grain");

        for (std::size_t local = 0; local < got; local += grain) {
            const auto bytes = std::min(grain, got - local);

            pending.emplace_back(
                parent_span.begin()
                    + static_cast<std::ptrdiff_t>(local),
                parent_span.begin()
                    + static_cast<std::ptrdiff_t>(local + bytes));

            scheduled_bytes += bytes;

            if (pending.size() >= workers) {
                flush_pending();

                if (options.operation) {
                    options.operation->report({
                        OperationPhase::Compressing,
                        input.size()
                            ? static_cast<double>(scheduled_bytes)
                                / static_cast<double>(input.size())
                            : 1.0,
                        scheduled_bytes,
                        input.size(),
                        {}
                    });
                }
            }
        }

        offset += got;
    }

    flush_pending();

    if (options.operation) {
        options.operation->report({
            OperationPhase::Compressing,
            1.0,
            input.size(),
            input.size(),
            {}
        });
    }

    if (entries.size() > std::numeric_limits<std::uint32_t>::max())
        throw std::runtime_error("K75 entry count overflow");

    std::vector<std::uint8_t> blob{'K','7','5','U'};
    put_u64(blob, input.size());
    put_u32(blob, static_cast<std::uint32_t>(entries.size()));

    for (const auto& entry : entries) {
        if (entry.compressed.size()
            > std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error(
                "K75 compressed entry too large");
        }

        blob.push_back(entry.mode);
        put_u32(blob, entry.raw_size);
        put_u32(
            blob,
            static_cast<std::uint32_t>(
                entry.compressed.size()));
        blob.insert(
            blob.end(),
            entry.compressed.begin(),
            entry.compressed.end());
    }

    BackendEncodeResult result;
    result.stats.input_bytes = input.size();
    result.stats.output_bytes = blob.size();
    result.stats.workers_used =
        entries.empty() ? 0 : workers;
    result.blob = std::move(blob);
    return result;
}

BackendStats NativeK75Backend::decode(
    std::span<const std::uint8_t> blob,
    std::uint64_t expected_raw_bytes,
    ByteSink& output,
    const BackendOptions& options) {

    if (options.operation) {
        options.operation->throw_if_cancelled();
    }

    if (blob.size() < 16
        || blob[0] != 'K' || blob[1] != '7'
        || blob[2] != '5' || blob[3] != 'U')
        throw std::runtime_error("not a K75U backend blob");

    struct EntryView {
        std::uint8_t mode{0};
        std::uint32_t raw_size{0};
        std::size_t compressed_offset{0};
        std::uint32_t compressed_size{0};
    };

    std::size_t pos = 4;
    const auto total_raw = get_u64(blob, pos);
    const auto count = get_u32(blob, pos);

    if (expected_raw_bytes != 0 && expected_raw_bytes != total_raw)
        throw std::runtime_error("K75 expected raw length mismatch");

    std::vector<EntryView> entries;
    entries.reserve(count);

    std::uint64_t declared_raw = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        if (pos >= blob.size())
            throw std::runtime_error("truncated K75 entry");

        EntryView entry;
        entry.mode = blob[pos++];
        entry.raw_size = get_u32(blob, pos);
        entry.compressed_size = get_u32(blob, pos);

        if (entry.compressed_size > blob.size() - pos)
            throw std::runtime_error("truncated K75 compressed payload");

        entry.compressed_offset = pos;
        pos += entry.compressed_size;

        if (entry.raw_size > total_raw - declared_raw)
            throw std::runtime_error("K75 declared raw length overflow");
        declared_raw += entry.raw_size;
        entries.push_back(entry);
    }

    if (declared_raw != total_raw)
        throw std::runtime_error("K75 declared total length mismatch");
    if (pos != blob.size())
        throw std::runtime_error("K75 trailing bytes");

    std::size_t workers = options.workers;
    if (workers == 0) {
        workers = std::thread::hardware_concurrency();
        if (workers == 0) workers = 1;
    }
    workers = std::clamp<std::size_t>(workers, 1, 16);
    workers = std::min<std::size_t>(workers, entries.size() ? entries.size() : 1);

    std::uint64_t output_offset = 0;

    if (options.operation) {
        options.operation->report({
            OperationPhase::Extracting,
            0.0,
            0,
            total_raw,
            {}
        });
    }

    for (std::size_t batch = 0; batch < entries.size(); batch += workers) {
        if (options.operation) {
            options.operation->throw_if_cancelled();
        }

        const auto batch_count =
            std::min<std::size_t>(workers, entries.size() - batch);

        std::vector<std::future<std::vector<std::uint8_t>>> futures;
        futures.reserve(batch_count);

        for (std::size_t j = 0; j < batch_count; ++j) {
            const auto entry = entries[batch + j];
            futures.push_back(std::async(
                std::launch::async,
                [blob, entry]() {
                    const auto compressed = blob.subspan(
                        entry.compressed_offset,
                        entry.compressed_size);
                    auto transformed =
                        native37::decode_aur2_blob(compressed);
                    auto raw =
                        inverse(transformed, entry.mode, entry.raw_size);
                    if (raw.size() != entry.raw_size)
                        throw std::runtime_error(
                            "K75 inverse transform length mismatch");
                    return raw;
                }));
        }

        for (auto& future : futures) {
            if (options.operation) {
                options.operation->throw_if_cancelled();
            }

            auto raw = future.get();

            if (output_offset > total_raw
                || raw.size() > total_raw - output_offset) {
                throw std::runtime_error("K75 decoded output overflow");
            }

            output.write(output_offset, raw);
            output_offset += raw.size();

            if (options.operation) {
                options.operation->report({
                    OperationPhase::Extracting,
                    total_raw
                        ? static_cast<double>(output_offset)
                            / static_cast<double>(total_raw)
                        : 1.0,
                    output_offset,
                    total_raw,
                    {}
                });
            }
        }
    }

    if (output_offset != total_raw)
        throw std::runtime_error("K75 decoded total length mismatch");

    BackendStats stats;
    stats.input_bytes = blob.size();
    stats.output_bytes = total_raw;
    stats.workers_used = entries.empty() ? 0 : workers;
    return stats;
}

} // namespace kephir2
