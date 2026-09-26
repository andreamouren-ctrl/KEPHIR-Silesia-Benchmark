#include "kephir2/native37_blob.hpp"

#include "kephir2/native37.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace kephir2::native37 {
namespace {

constexpr std::size_t kChunkBytes = 512u * 1024u;
constexpr std::uint32_t kAur2Version = 4u;
constexpr std::string_view kInnerName = "payload.bin";

void put_u32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    for (unsigned k = 0; k < 4; ++k) {
        out.push_back(static_cast<std::uint8_t>(value >> (8u * k)));
    }
}

void put_u64(std::vector<std::uint8_t>& out, std::uint64_t value) {
    for (unsigned k = 0; k < 8; ++k) {
        out.push_back(static_cast<std::uint8_t>(value >> (8u * k)));
    }
}

std::uint32_t get_u32(
    std::span<const std::uint8_t> data,
    std::size_t& pos) {

    if (data.size() - pos < 4) {
        throw std::runtime_error("truncated AUR2 u32");
    }

    std::uint32_t value = 0;
    for (unsigned k = 0; k < 4; ++k) {
        value |= static_cast<std::uint32_t>(data[pos++]) << (8u * k);
    }
    return value;
}

std::uint64_t get_u64(
    std::span<const std::uint8_t> data,
    std::size_t& pos) {

    if (data.size() - pos < 8) {
        throw std::runtime_error("truncated AUR2 u64");
    }

    std::uint64_t value = 0;
    for (unsigned k = 0; k < 8; ++k) {
        value |= static_cast<std::uint64_t>(data[pos++]) << (8u * k);
    }
    return value;
}

} // namespace

std::vector<std::uint8_t> encode_aur2_blob(
    std::span<const std::uint8_t> raw) {

    if (raw.size() > std::numeric_limits<std::uint64_t>::max()) {
        throw std::runtime_error("AUR2 raw input too large");
    }

    const std::uint64_t raw_size = raw.size();
    const std::uint64_t chunks64 =
        raw_size == 0 ? 0 : (raw_size + kChunkBytes - 1) / kChunkBytes;

    if (chunks64 > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("AUR2 chunk count overflow");
    }

    std::vector<std::vector<std::uint8_t>> compressed;
    compressed.reserve(static_cast<std::size_t>(chunks64));

    for (std::size_t offset = 0; offset < raw.size(); offset += kChunkBytes) {
        const auto bytes = std::min(kChunkBytes, raw.size() - offset);
        std::vector<std::uint8_t> chunk(
            raw.begin() + static_cast<std::ptrdiff_t>(offset),
            raw.begin() + static_cast<std::ptrdiff_t>(offset + bytes));
        compressed.push_back(compress_chunk(chunk));
    }

    std::vector<std::uint8_t> out;
    out.insert(out.end(), {'A','U','R','2'});
    put_u32(out, kAur2Version);
    put_u32(out, 1u);
    put_u64(out, raw_size);
    put_u32(out, static_cast<std::uint32_t>(compressed.size()));

    put_u32(out, static_cast<std::uint32_t>(kInnerName.size()));
    out.insert(out.end(), kInnerName.begin(), kInnerName.end());
    put_u64(out, raw_size);

    std::size_t offset = 0;
    for (const auto& comp : compressed) {
        const auto bytes = std::min(kChunkBytes, raw.size() - offset);
        if (bytes > std::numeric_limits<std::uint32_t>::max()
            || comp.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error("AUR2 chunk length overflow");
        }

        put_u32(out, static_cast<std::uint32_t>(bytes));
        put_u32(out, static_cast<std::uint32_t>(comp.size()));
        out.insert(out.end(), comp.begin(), comp.end());
        offset += bytes;
    }

    return out;
}

std::vector<std::uint8_t> decode_aur2_blob(
    std::span<const std::uint8_t> blob) {

    if (blob.size() < 24
        || blob[0] != 'A'
        || blob[1] != 'U'
        || blob[2] != 'R'
        || blob[3] != '2') {
        throw std::runtime_error("not an AUR2 blob");
    }

    std::size_t pos = 4;
    const auto version = get_u32(blob, pos);
    if (version < 2 || version > 4) {
        throw std::runtime_error("unsupported AUR2 version");
    }

    const auto entries = get_u32(blob, pos);
    if (entries != 1) {
        throw std::runtime_error("AUR2 backend blob must contain one entry");
    }

    const auto total_raw = get_u64(blob, pos);
    const auto chunk_count = get_u32(blob, pos);

    const auto name_length = get_u32(blob, pos);
    if (name_length > blob.size() - pos) {
        throw std::runtime_error("truncated AUR2 entry name");
    }
    pos += name_length;

    const auto entry_raw = get_u64(blob, pos);
    if (entry_raw != total_raw) {
        throw std::runtime_error("AUR2 entry/raw length mismatch");
    }
    if (total_raw > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("AUR2 raw output too large for process");
    }

    std::vector<std::uint8_t> out;
    out.reserve(static_cast<std::size_t>(total_raw));

    for (std::uint32_t i = 0; i < chunk_count; ++i) {
        const auto raw_size = get_u32(blob, pos);
        const auto comp_size = get_u32(blob, pos);

        if (comp_size > blob.size() - pos) {
            throw std::runtime_error("truncated AUR2 chunk payload");
        }

        std::vector<std::uint8_t> comp(
            blob.begin() + static_cast<std::ptrdiff_t>(pos),
            blob.begin() + static_cast<std::ptrdiff_t>(pos + comp_size));
        pos += comp_size;

        auto raw = decompress_chunk(comp, raw_size);
        if (raw.size() != raw_size) {
            throw std::runtime_error("AUR2 decoded chunk length mismatch");
        }

        if (raw.size() > static_cast<std::size_t>(total_raw) - out.size()) {
            throw std::runtime_error("AUR2 decoded raw length overflow");
        }
        out.insert(out.end(), raw.begin(), raw.end());
    }

    if (out.size() != total_raw) {
        throw std::runtime_error("AUR2 raw length mismatch");
    }
    if (pos != blob.size()) {
        throw std::runtime_error("AUR2 trailing bytes");
    }

    return out;
}

} // namespace kephir2::native37
