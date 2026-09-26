#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace kephir2 {

using ByteBuffer = std::vector<std::uint8_t>;

struct ManifestRecord {
    std::string path;
    std::uint64_t group_id{0};
    std::uint64_t size{0};

    bool operator==(const ManifestRecord&) const = default;
};

enum class Kpf1Kind : std::uint8_t {
    File = 0,
    Directory = 1
};

struct Kpf1FileEnvelope {
    std::string name;
    ByteBuffer compressed_blob;

    bool operator==(const Kpf1FileEnvelope&) const = default;
};

struct Kpf1GroupEnvelope {
    std::uint64_t raw_length{0};
    ByteBuffer compressed_blob;

    bool operator==(const Kpf1GroupEnvelope&) const = default;
};

struct Kpf1DirectoryEnvelope {
    std::vector<std::string> group_names;
    ByteBuffer manifest;
    std::vector<Kpf1GroupEnvelope> groups;

    bool operator==(const Kpf1DirectoryEnvelope&) const = default;
};

void put_varint(ByteBuffer& out, std::uint64_t value);
[[nodiscard]] std::uint64_t get_varint(
    std::span<const std::uint8_t> data,
    std::size_t& position);

[[nodiscard]] std::size_t common_prefix_bytes(
    std::string_view a,
    std::string_view b) noexcept;

[[nodiscard]] ByteBuffer encode_manifest(
    std::span<const ManifestRecord> records);

[[nodiscard]] std::vector<ManifestRecord> decode_manifest(
    std::span<const std::uint8_t> data,
    std::uint64_t group_count);

[[nodiscard]] ByteBuffer encode_kpf1_file(
    const Kpf1FileEnvelope& envelope);

[[nodiscard]] Kpf1FileEnvelope decode_kpf1_file(
    std::span<const std::uint8_t> data);

[[nodiscard]] ByteBuffer encode_kpf1_directory(
    const Kpf1DirectoryEnvelope& envelope);

[[nodiscard]] Kpf1DirectoryEnvelope decode_kpf1_directory(
    std::span<const std::uint8_t> data);

[[nodiscard]] std::filesystem::path safe_archive_target(
    const std::filesystem::path& root,
    std::string_view relative_utf8);

[[nodiscard]] std::vector<std::filesystem::path> collect_directory_files(
    const std::filesystem::path& root);

} // namespace kephir2
