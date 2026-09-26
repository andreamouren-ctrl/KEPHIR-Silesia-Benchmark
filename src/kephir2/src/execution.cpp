#include "kephir2/execution.hpp"

#include "kephir2/packing.hpp"

#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace kephir2 {
namespace {

class FileByteSource final : public ByteSource {
public:
    explicit FileByteSource(std::filesystem::path path)
        : path_(std::move(path)),
          size_(std::filesystem::file_size(path_)) {}

    [[nodiscard]] std::uint64_t size() const noexcept override {
        return size_;
    }

    [[nodiscard]] std::size_t read(
        std::uint64_t offset,
        std::span<std::uint8_t> destination) const override {

        if (destination.empty() || offset >= size_) {
            return 0;
        }

        const auto bytes = static_cast<std::size_t>(
            std::min<std::uint64_t>(size_ - offset, destination.size()));

        std::ifstream in(path_, std::ios::binary);
        if (!in) {
            throw std::runtime_error("unable to open file byte source");
        }

        in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!in) {
            throw std::runtime_error("unable to seek file byte source");
        }

        in.read(
            reinterpret_cast<char*>(destination.data()),
            static_cast<std::streamsize>(bytes));

        if (in.gcount() != static_cast<std::streamsize>(bytes)) {
            throw std::runtime_error("short read from file byte source");
        }

        return bytes;
    }

private:
    std::filesystem::path path_;
    std::uint64_t size_{0};
};

class FileByteSink final : public ByteSink {
public:
    explicit FileByteSink(std::filesystem::path path)
        : path_(std::move(path)) {

        std::filesystem::create_directories(path_.parent_path());
        std::ofstream out(path_, std::ios::binary | std::ios::trunc);
        if (!out) {
            throw std::runtime_error("unable to create file byte sink");
        }
    }

    void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) override {

        if (source.empty()) {
            return;
        }

        std::fstream out(
            path_,
            std::ios::binary | std::ios::in | std::ios::out);
        if (!out) {
            throw std::runtime_error("unable to open file byte sink");
        }

        out.seekp(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!out) {
            throw std::runtime_error("unable to seek file byte sink");
        }

        out.write(
            reinterpret_cast<const char*>(source.data()),
            static_cast<std::streamsize>(source.size()));
        if (!out) {
            throw std::runtime_error("unable to write file byte sink");
        }

        const auto end = offset + source.size();
        if (end > size_) {
            size_ = end;
        }
    }

    [[nodiscard]] std::uint64_t size() const noexcept {
        return size_;
    }

private:
    std::filesystem::path path_;
    std::uint64_t size_{0};
};

std::string filename_utf8(const std::filesystem::path& path) {
    const auto u8 = path.filename().generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(u8.data()),
        u8.size());
}

} // namespace

ByteBuffer ArchiveExecutor::compress_file(
    const std::filesystem::path& input,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    if (!std::filesystem::is_regular_file(input)) {
        throw std::runtime_error("compression input is not a regular file");
    }

    FileByteSource source(input);
    auto encoded = backend.encode(source, options);

    if (encoded.stats.input_bytes != 0
        && encoded.stats.input_bytes != source.size()) {
        throw std::runtime_error("backend reported inconsistent input length");
    }

    return encode_kpf1_file({
        filename_utf8(input),
        std::move(encoded.blob)
    });
}

ByteBuffer ArchiveExecutor::compress_directory(
    const std::filesystem::path& root,
    CompressionBackend& backend,
    const BackendOptions& options,
    Layout layout) const {

    if (!std::filesystem::is_directory(root)) {
        throw std::runtime_error("compression input is not a directory");
    }

    if (layout == Layout::Hybrid) {
        throw std::runtime_error("HYBRID layout is not implemented");
    }

    const auto plan = layout == Layout::Flat
        ? build_flat_directory_packing_plan(root)
        : build_directory_packing_plan(root);

    Kpf1DirectoryEnvelope envelope;
    envelope.manifest = plan.manifest;
    envelope.group_names.reserve(plan.groups.size());
    envelope.groups.reserve(plan.groups.size());

    for (std::size_t i = 0; i < plan.groups.size(); ++i) {
        const auto& group = plan.groups[i];
        envelope.group_names.push_back(group.name);

        PackedGroupSource source(root, plan, i);
        auto encoded = backend.encode(source, options);

        if (encoded.stats.input_bytes != 0
            && encoded.stats.input_bytes != group.raw_length) {
            throw std::runtime_error("backend reported inconsistent group input length");
        }

        envelope.groups.push_back({
            group.raw_length,
            std::move(encoded.blob)
        });
    }

    return encode_kpf1_directory(envelope);
}

void ArchiveExecutor::extract_file(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    const auto envelope = decode_kpf1_file(archive);

    std::filesystem::create_directories(output_directory);
    const auto target = safe_archive_target(
        output_directory,
        envelope.name);

    FileByteSink sink(target);
    const auto stats = backend.decode(
        envelope.compressed_blob,
        0,
        sink,
        options);

    if (stats.output_bytes != 0 && stats.output_bytes != sink.size()) {
        throw std::runtime_error("backend reported inconsistent file output length");
    }
}

void ArchiveExecutor::extract_directory(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    const auto envelope = decode_kpf1_directory(archive);
    const auto records = decode_manifest(
        envelope.manifest,
        envelope.group_names.size());

    std::filesystem::create_directories(output_directory);

    for (std::size_t i = 0; i < envelope.groups.size(); ++i) {
        const auto& group = envelope.groups[i];

        PackedGroupSink sink(
            output_directory,
            records,
            i,
            group.raw_length);

        const auto stats = backend.decode(
            group.compressed_blob,
            group.raw_length,
            sink,
            options);

        if (stats.output_bytes != 0
            && stats.output_bytes != group.raw_length) {
            throw std::runtime_error("backend reported inconsistent group output length");
        }
    }
}

} // namespace kephir2
