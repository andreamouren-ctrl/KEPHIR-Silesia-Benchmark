#include "kephir2/archive.hpp"

#include <algorithm>
#include <array>
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

ByteBuffer encode_kpf1_file(const Kpf1FileEnvelope& envelope) {
    ByteBuffer out{'K', 'P', 'F', '1', static_cast<std::uint8_t>(Kpf1Kind::File)};

    put_varint(out, envelope.name.size());
    out.insert(
        out.end(),
        reinterpret_cast<const std::uint8_t*>(envelope.name.data()),
        reinterpret_cast<const std::uint8_t*>(envelope.name.data() + envelope.name.size()));

    put_varint(out, envelope.compressed_blob.size());
    out.insert(out.end(), envelope.compressed_blob.begin(), envelope.compressed_blob.end());
    return out;
}

Kpf1FileEnvelope decode_kpf1_file(std::span<const std::uint8_t> data) {
    static constexpr std::array<std::uint8_t, 4> magic{'K', 'P', 'F', '1'};

    if (data.size() < 5 || !std::equal(magic.begin(), magic.end(), data.begin())) {
        throw std::runtime_error("not a KPF1 archive");
    }
    if (data[4] != static_cast<std::uint8_t>(Kpf1Kind::File)) {
        throw std::runtime_error("KPF1 archive is not a file envelope");
    }

    std::size_t pos = 5;
    const auto name_length = get_varint(data, pos);
    if (name_length > data.size() - pos) {
        throw std::runtime_error("truncated KPF1 file name");
    }

    std::string name(
        reinterpret_cast<const char*>(data.data() + pos),
        static_cast<std::size_t>(name_length));
    pos += static_cast<std::size_t>(name_length);

    const auto blob_length = get_varint(data, pos);
    if (blob_length > data.size() - pos) {
        throw std::runtime_error("truncated KPF1 file payload");
    }

    ByteBuffer blob(
        data.begin() + static_cast<std::ptrdiff_t>(pos),
        data.begin() + static_cast<std::ptrdiff_t>(pos + static_cast<std::size_t>(blob_length)));
    pos += static_cast<std::size_t>(blob_length);

    if (pos != data.size()) {
        throw std::runtime_error("KPF1 file trailing bytes");
    }

    return {std::move(name), std::move(blob)};
}

ByteBuffer encode_kpf1_directory(const Kpf1DirectoryEnvelope& envelope) {
    if (envelope.group_names.size() != envelope.groups.size()) {
        throw std::runtime_error("KPF1 directory group table/payload count mismatch");
    }

    // Validate manifest structure and group references before emission.
    (void)decode_manifest(envelope.manifest, envelope.group_names.size());

    ByteBuffer out{'K', 'P', 'F', '1', static_cast<std::uint8_t>(Kpf1Kind::Directory)};
    put_varint(out, envelope.group_names.size());

    for (const auto& name : envelope.group_names) {
        put_varint(out, name.size());
        out.insert(
            out.end(),
            reinterpret_cast<const std::uint8_t*>(name.data()),
            reinterpret_cast<const std::uint8_t*>(name.data() + name.size()));
    }

    put_varint(out, envelope.manifest.size());
    out.insert(out.end(), envelope.manifest.begin(), envelope.manifest.end());

    for (const auto& group : envelope.groups) {
        put_varint(out, group.raw_length);
        put_varint(out, group.compressed_blob.size());
        out.insert(
            out.end(),
            group.compressed_blob.begin(),
            group.compressed_blob.end());
    }

    return out;
}

Kpf1DirectoryEnvelope decode_kpf1_directory(std::span<const std::uint8_t> data) {
    static constexpr std::array<std::uint8_t, 4> magic{'K', 'P', 'F', '1'};

    if (data.size() < 5 || !std::equal(magic.begin(), magic.end(), data.begin())) {
        throw std::runtime_error("not a KPF1 archive");
    }
    if (data[4] != static_cast<std::uint8_t>(Kpf1Kind::Directory)) {
        throw std::runtime_error("KPF1 archive is not a directory envelope");
    }

    std::size_t pos = 5;
    const auto group_count = get_varint(data, pos);
    if (group_count > data.size()) {
        throw std::runtime_error("KPF1 group count is not plausible");
    }

    Kpf1DirectoryEnvelope envelope;
    envelope.group_names.reserve(static_cast<std::size_t>(group_count));
    envelope.groups.reserve(static_cast<std::size_t>(group_count));

    for (std::uint64_t i = 0; i < group_count; ++i) {
        const auto name_length = get_varint(data, pos);
        if (name_length > data.size() - pos) {
            throw std::runtime_error("truncated KPF1 group name");
        }

        envelope.group_names.emplace_back(
            reinterpret_cast<const char*>(data.data() + pos),
            static_cast<std::size_t>(name_length));
        pos += static_cast<std::size_t>(name_length);
    }

    const auto manifest_length = get_varint(data, pos);
    if (manifest_length > data.size() - pos) {
        throw std::runtime_error("truncated KPF1 manifest");
    }

    envelope.manifest.assign(
        data.begin() + static_cast<std::ptrdiff_t>(pos),
        data.begin() + static_cast<std::ptrdiff_t>(pos + static_cast<std::size_t>(manifest_length)));
    pos += static_cast<std::size_t>(manifest_length);

    // Validate manifest before accepting group payloads.
    (void)decode_manifest(envelope.manifest, group_count);

    for (std::uint64_t i = 0; i < group_count; ++i) {
        const auto raw_length = get_varint(data, pos);
        const auto blob_length = get_varint(data, pos);
        if (blob_length > data.size() - pos) {
            throw std::runtime_error("truncated KPF1 group payload");
        }

        ByteBuffer blob(
            data.begin() + static_cast<std::ptrdiff_t>(pos),
            data.begin() + static_cast<std::ptrdiff_t>(pos + static_cast<std::size_t>(blob_length)));
        pos += static_cast<std::size_t>(blob_length);

        envelope.groups.push_back({raw_length, std::move(blob)});
    }

    if (pos != data.size()) {
        throw std::runtime_error("KPF1 directory trailing bytes");
    }

    return envelope;
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
