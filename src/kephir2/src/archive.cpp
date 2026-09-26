#include "kephir2/archive.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <system_error>

namespace kephir2 {

void put_varint(ByteBuffer& out, std::uint64_t value) {
    for (;;) {
        const auto byte = static_cast<std::uint8_t>(value & 0x7fu);
        value >>= 7u;
        if (value != 0) {
            out.push_back(static_cast<std::uint8_t>(byte | 0x80u));
        } else {
            out.push_back(byte);
            return;
        }
    }
}

std::uint64_t get_varint(
    std::span<const std::uint8_t> data,
    std::size_t& position) {

    std::uint64_t value = 0;
    unsigned shift = 0;

    for (unsigned i = 0; i < 10; ++i) {
        if (position >= data.size()) {
            throw std::runtime_error("truncated varint");
        }

        const std::uint8_t byte = data[position++];
        const std::uint64_t payload = static_cast<std::uint64_t>(byte & 0x7fu);

        if (shift == 63u && payload > 1u) {
            throw std::runtime_error("varint overflow");
        }

        value |= payload << shift;

        if ((byte & 0x80u) == 0) {
            return value;
        }

        shift += 7u;
    }

    throw std::runtime_error("varint overflow");
}

std::size_t common_prefix_bytes(
    std::string_view a,
    std::string_view b) noexcept {

    const auto n = std::min(a.size(), b.size());
    std::size_t i = 0;
    while (i < n && a[i] == b[i]) {
        ++i;
    }
    return i;
}

ByteBuffer encode_manifest(std::span<const ManifestRecord> records) {
    ByteBuffer out;
    put_varint(out, records.size());

    std::string previous;
    for (const auto& record : records) {
        const auto prefix = common_prefix_bytes(previous, record.path);
        const std::string_view suffix(record.path.data() + prefix, record.path.size() - prefix);

        put_varint(out, prefix);
        put_varint(out, suffix.size());
        out.insert(
            out.end(),
            reinterpret_cast<const std::uint8_t*>(suffix.data()),
            reinterpret_cast<const std::uint8_t*>(suffix.data() + suffix.size()));
        put_varint(out, record.group_id);
        put_varint(out, record.size);

        previous = record.path;
    }

    return out;
}

std::vector<ManifestRecord> decode_manifest(
    std::span<const std::uint8_t> data,
    std::uint64_t group_count) {

    std::size_t pos = 0;
    const auto count = get_varint(data, pos);

    if (count > data.size()) {
        throw std::runtime_error("manifest record count is not plausible");
    }

    std::vector<ManifestRecord> records;
    records.reserve(static_cast<std::size_t>(count));

    std::string previous;

    for (std::uint64_t i = 0; i < count; ++i) {
        const auto prefix = get_varint(data, pos);
        const auto suffix_length = get_varint(data, pos);

        if (prefix > previous.size()) {
            throw std::runtime_error("manifest prefix exceeds previous path");
        }
        if (suffix_length > data.size() - pos) {
            throw std::runtime_error("truncated manifest path suffix");
        }

        std::string path = previous.substr(0, static_cast<std::size_t>(prefix));
        path.append(
            reinterpret_cast<const char*>(data.data() + pos),
            static_cast<std::size_t>(suffix_length));
        pos += static_cast<std::size_t>(suffix_length);

        const auto group_id = get_varint(data, pos);
        const auto size = get_varint(data, pos);

        if (group_id >= group_count) {
            throw std::runtime_error("manifest group id out of range");
        }

        records.push_back({path, group_id, size});
        previous = std::move(path);
    }

    if (pos != data.size()) {
        throw std::runtime_error("manifest trailing bytes");
    }

    return records;
}

std::filesystem::path safe_archive_target(
    const std::filesystem::path& root,
    std::string_view relative_utf8) {

    if (relative_utf8.empty()) {
        throw std::runtime_error("empty archive path");
    }

    const auto rel = std::filesystem::u8path(
        relative_utf8.begin(),
        relative_utf8.end());

    if (rel.is_absolute() || rel.has_root_name() || rel.has_root_directory()) {
        throw std::runtime_error("unsafe archive path");
    }

    for (const auto& part : rel) {
        if (part == "..") {
            throw std::runtime_error("unsafe archive path");
        }
    }

    std::error_code ec;
    const auto root_canonical = std::filesystem::weakly_canonical(root, ec);
    if (ec) {
        throw std::runtime_error("unable to canonicalize archive root");
    }

    const auto destination = std::filesystem::weakly_canonical(root_canonical / rel, ec);
    if (ec) {
        throw std::runtime_error("unable to canonicalize archive target");
    }

    auto r = root_canonical.begin();
    auto d = destination.begin();
    for (; r != root_canonical.end(); ++r, ++d) {
        if (d == destination.end() || *r != *d) {
            throw std::runtime_error("unsafe archive path");
        }
    }

    return destination;
}

std::vector<std::filesystem::path> collect_directory_files(
    const std::filesystem::path& root) {

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

} // namespace kephir2
