#include "kephir2/aur2_execution.hpp"

#include "kephir2/archive.hpp"
#include "kephir2/packing.hpp"

#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace kephir2::aur2 {
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
            throw std::runtime_error("unable to open AUR2 file byte source");
        }

        in.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!in) {
            throw std::runtime_error("unable to seek AUR2 file byte source");
        }

        in.read(
            reinterpret_cast<char*>(destination.data()),
            static_cast<std::streamsize>(bytes));

        if (in.gcount() != static_cast<std::streamsize>(bytes)) {
            throw std::runtime_error("short read from AUR2 file byte source");
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
            throw std::runtime_error("unable to create AUR2 file byte sink");
        }
    }

    void write(
        std::uint64_t offset,
        std::span<const std::uint8_t> source) override {

        if (source.empty()) {
            return;
        }

        std::fstream out(path_, std::ios::binary | std::ios::in | std::ios::out);
        if (!out) {
            throw std::runtime_error("unable to open AUR2 file byte sink");
        }

        out.seekp(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!out) {
            throw std::runtime_error("unable to seek AUR2 file byte sink");
        }

        out.write(
            reinterpret_cast<const char*>(source.data()),
            static_cast<std::streamsize>(source.size()));
        if (!out) {
            throw std::runtime_error("unable to write AUR2 file byte sink");
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

std::string path_utf8(const std::filesystem::path& path) {
    const auto u8 = path.generic_u8string();
    return std::string(
        reinterpret_cast<const char*>(u8.data()),
        u8.size());
}

std::string filename_utf8(const std::filesystem::path& path) {
    return path_utf8(path.filename());
}

std::string relative_utf8(
    const std::filesystem::path& path,
    const std::filesystem::path& root) {
    return path_utf8(path.lexically_relative(root));
}

std::vector<std::string> collect_directory_entries(const std::filesystem::path& root) {
    std::vector<std::string> directories;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_symlink()) {
            continue;
        }
        if (entry.is_directory()) {
            directories.push_back(relative_utf8(entry.path(), root));
        }
    }
    std::sort(directories.begin(), directories.end());
    return directories;
}

ByteBuffer encode_backend_format_version(std::uint32_t version) {
    return ByteBuffer{
        static_cast<std::uint8_t>(version & 0xffu),
        static_cast<std::uint8_t>((version >> 8u) & 0xffu),
        static_cast<std::uint8_t>((version >> 16u) & 0xffu),
        static_cast<std::uint8_t>((version >> 24u) & 0xffu),
    };
}

std::uint32_t decode_backend_format_version(std::span<const std::uint8_t> data) {
    if (data.size() != 4) {
        throw std::runtime_error("unsupported AUR2 KEPHIR codec descriptor payload");
    }
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8u) |
           (static_cast<std::uint32_t>(data[2]) << 16u) |
           (static_cast<std::uint32_t>(data[3]) << 24u);
}

CodecDescriptor make_kephir_descriptor(const CompressionBackend& backend) {
    CodecDescriptor descriptor;
    descriptor.codec_id = kCodecKephir;
    descriptor.codec_major = 2;
    descriptor.codec_minor = 0;
    descriptor.minimum_decoder_major = 2;
    descriptor.minimum_decoder_minor = 0;
    descriptor.private_data = encode_backend_format_version(backend.format_version());
    return descriptor;
}

const Section& find_required_section(const Container& container, SectionType type) {
    const auto raw = static_cast<std::uint32_t>(type);
    const Section* found = nullptr;
    for (const auto& section : container.sections) {
        if (section.type != raw) continue;
        if (found != nullptr) {
            throw std::runtime_error("duplicate required AUR2 section");
        }
        found = &section;
    }
    if (found == nullptr) {
        throw std::runtime_error("missing required AUR2 section");
    }
    return *found;
}

void verify_kephir_descriptor(
    const Container& container,
    const CompressionBackend& backend) {

    const auto descriptor = decode_codec_descriptor(
        find_required_section(container, SectionType::CodecDescriptor).payload);
    if (descriptor.codec_id != kCodecKephir) {
        throw std::runtime_error("AUR2 archive uses unsupported codec");
    }
    const auto required_backend_format =
        decode_backend_format_version(descriptor.private_data);
    if (required_backend_format != backend.format_version()) {
        throw std::runtime_error("AUR2 KEPHIR backend format version mismatch");
    }
}

std::vector<Section> build_required_sections(
    const CodecDescriptor& descriptor,
    std::span<const FileEntry> entries,
    std::span<const StreamRecord> streams,
    ByteBuffer data) {

    std::vector<Section> sections;
    sections.push_back({
        static_cast<std::uint32_t>(SectionType::FileTable),
        SectionFlagRequired,
        encode_file_table(entries)
    });
    sections.push_back({
        static_cast<std::uint32_t>(SectionType::CodecDescriptor),
        SectionFlagRequired,
        encode_codec_descriptor(descriptor)
    });
    sections.push_back({
        static_cast<std::uint32_t>(SectionType::BlockTable),
        SectionFlagRequired,
        encode_stream_table(streams)
    });
    sections.push_back({
        static_cast<std::uint32_t>(SectionType::Data),
        SectionFlagRequired,
        std::move(data)
    });
    return sections;
}

std::span<const std::uint8_t> stream_blob(
    const Section& data,
    const StreamRecord& stream) {

    if (stream.payload_offset > data.payload.size() ||
        stream.compressed_size > data.payload.size() - stream.payload_offset) {
        throw std::runtime_error("AUR2 compressed stream range exceeds DATA section");
    }
    const auto begin = static_cast<std::size_t>(stream.payload_offset);
    const auto size = static_cast<std::size_t>(stream.compressed_size);
    return std::span<const std::uint8_t>(data.payload.data() + begin, size);
}

} // namespace

ByteBuffer ArchiveExecutor::compress_file(
    const std::filesystem::path& input,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    if (!std::filesystem::is_regular_file(input)) {
        throw std::runtime_error("AUR2 compression input is not a regular file");
    }

    FileByteSource source(input);
    const auto descriptor = make_kephir_descriptor(backend);

    FileEntry entry;
    entry.entry_id = 1;
    entry.type = EntryType::File;
    entry.path = filename_utf8(input);
    entry.logical_size = source.size();

    std::vector<StreamRecord> streams;
    ByteBuffer data;

    if (source.size() != 0) {
        auto encoded = backend.encode(source, options);
        if (encoded.stats.input_bytes != 0 && encoded.stats.input_bytes != source.size()) {
            throw std::runtime_error("backend reported inconsistent AUR2 input length");
        }
        if (encoded.blob.empty()) {
            throw std::runtime_error("backend returned empty AUR2 payload for non-empty input");
        }

        entry.stream_id = 1;
        streams.push_back({
            1,
            0,
            encoded.blob.size(),
            source.size(),
            kCodecKephir,
            0
        });
        data = std::move(encoded.blob);
    }

    Header header;
    header.logical_size = source.size();
    header.feature_flags = feature_bit(Feature::Kephir2);

    const std::vector<FileEntry> entries{entry};
    auto sections = build_required_sections(descriptor, entries, streams, std::move(data));
    Container model{header, sections};
    validate_container_structure(model);
    return encode_container(header, sections);
}

ByteBuffer ArchiveExecutor::compress_directory(
    const std::filesystem::path& root,
    CompressionBackend& backend,
    const BackendOptions& options,
    Layout layout) const {

    if (!std::filesystem::is_directory(root)) {
        throw std::runtime_error("AUR2 compression input is not a directory");
    }
    if (layout == Layout::Hybrid) {
        throw std::runtime_error("AUR2 HYBRID layout is not implemented");
    }

    const auto plan = layout == Layout::Flat
        ? build_flat_directory_packing_plan(root)
        : build_directory_packing_plan(root);

    const auto descriptor = make_kephir_descriptor(backend);
    std::vector<StreamRecord> streams;
    ByteBuffer data;
    std::vector<bool> group_has_stream(plan.groups.size(), false);

    for (std::size_t i = 0; i < plan.groups.size(); ++i) {
        const auto& group = plan.groups[i];
        if (group.raw_length == 0) {
            continue;
        }

        PackedGroupSource source(root, plan, i);
        auto encoded = backend.encode(source, options);
        if (encoded.stats.input_bytes != 0 && encoded.stats.input_bytes != group.raw_length) {
            throw std::runtime_error("backend reported inconsistent AUR2 group input length");
        }
        if (encoded.blob.empty()) {
            throw std::runtime_error("backend returned empty AUR2 group payload");
        }

        const std::uint64_t stream_id = static_cast<std::uint64_t>(i) + 1;
        streams.push_back({
            stream_id,
            data.size(),
            encoded.blob.size(),
            group.raw_length,
            kCodecKephir,
            0
        });
        data.insert(data.end(), encoded.blob.begin(), encoded.blob.end());
        group_has_stream[i] = true;
    }

    std::vector<FileEntry> entries;
    std::uint64_t next_entry_id = 1;

    for (const auto& directory : collect_directory_entries(root)) {
        entries.push_back({
            next_entry_id++,
            EntryType::Directory,
            directory,
            0,
            0,
            0,
            0,
            0
        });
    }

    std::uint64_t logical_size = 0;
    for (const auto& file : plan.files) {
        if (file.size > std::numeric_limits<std::uint64_t>::max() - logical_size) {
            throw std::runtime_error("AUR2 directory logical size overflow");
        }
        logical_size += file.size;

        const auto group_index = static_cast<std::size_t>(file.group_id);
        if (group_index >= group_has_stream.size()) {
            throw std::runtime_error("AUR2 packing group id out of range");
        }

        const auto stream_id = group_has_stream[group_index]
            ? file.group_id + 1
            : 0;
        const auto stream_offset = stream_id != 0 ? file.group_offset : 0;

        entries.push_back({
            next_entry_id++,
            EntryType::File,
            file.path,
            file.size,
            stream_id,
            stream_offset,
            0,
            0
        });
    }

    Header header;
    header.logical_size = logical_size;
    header.feature_flags =
        feature_bit(Feature::Directory) |
        feature_bit(Feature::Kephir2);
    if (streams.size() > 1) {
        header.feature_flags |= feature_bit(Feature::MultiStream);
    }

    auto sections = build_required_sections(descriptor, entries, streams, std::move(data));
    Container model{header, sections};
    validate_container_structure(model);
    return encode_container(header, sections);
}

void ArchiveExecutor::extract_file(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    const auto container = decode_container(archive);
    validate_container_structure(container);
    verify_kephir_descriptor(container, backend);

    const auto entries = decode_file_table(
        find_required_section(container, SectionType::FileTable).payload);
    if (entries.size() != 1 || entries[0].type != EntryType::File) {
        throw std::runtime_error("AUR2 file extractor requires exactly one file entry");
    }
    const auto& entry = entries[0];

    std::filesystem::create_directories(output_directory);
    const auto target = safe_archive_target(output_directory, entry.path);
    FileByteSink sink(target);

    if (entry.logical_size == 0 && entry.stream_id == 0) {
        return;
    }

    const auto streams = decode_stream_table(
        find_required_section(container, SectionType::BlockTable).payload);
    const auto& data = find_required_section(container, SectionType::Data);

    const StreamRecord* stream = nullptr;
    for (const auto& candidate : streams) {
        if (candidate.stream_id == entry.stream_id) {
            stream = &candidate;
            break;
        }
    }
    if (stream == nullptr) {
        throw std::runtime_error("AUR2 file stream was not found");
    }
    if (entry.stream_offset != 0 || entry.logical_size != stream->raw_size) {
        throw std::runtime_error("AUR2 single-file entry does not cover its complete stream");
    }

    const auto stats = backend.decode(
        stream_blob(data, *stream),
        stream->raw_size,
        sink,
        options);

    if (stats.output_bytes != 0 && stats.output_bytes != stream->raw_size) {
        throw std::runtime_error("backend reported inconsistent AUR2 output length");
    }
    if (sink.size() != entry.logical_size) {
        throw std::runtime_error("AUR2 extracted file size mismatch");
    }
}

void ArchiveExecutor::extract_directory(
    std::span<const std::uint8_t> archive,
    const std::filesystem::path& output_directory,
    CompressionBackend& backend,
    const BackendOptions& options) const {

    const auto container = decode_container(archive);
    validate_container_structure(container);
    verify_kephir_descriptor(container, backend);

    if ((container.header.feature_flags & feature_bit(Feature::Directory)) == 0) {
        throw std::runtime_error("AUR2 archive is not marked as a directory archive");
    }

    const auto entries = decode_file_table(
        find_required_section(container, SectionType::FileTable).payload);
    const auto streams = decode_stream_table(
        find_required_section(container, SectionType::BlockTable).payload);
    const auto& data = find_required_section(container, SectionType::Data);

    std::filesystem::create_directories(output_directory);

    std::vector<ManifestRecord> records;
    for (const auto& entry : entries) {
        if (entry.type == EntryType::Directory) {
            const auto target = safe_archive_target(output_directory, entry.path);
            std::filesystem::create_directories(target);
            continue;
        }

        if (entry.stream_id == 0) {
            if (entry.logical_size != 0) {
                throw std::runtime_error("AUR2 non-empty file has no stream");
            }
            const auto target = safe_archive_target(output_directory, entry.path);
            std::filesystem::create_directories(target.parent_path());
            std::ofstream out(target, std::ios::binary | std::ios::trunc);
            if (!out) {
                throw std::runtime_error("unable to create empty AUR2 extraction target");
            }
            continue;
        }

        records.push_back({entry.path, entry.stream_id, entry.logical_size});
    }

    for (const auto& stream : streams) {
        PackedGroupSink sink(
            output_directory,
            records,
            stream.stream_id,
            stream.raw_size);

        const auto stats = backend.decode(
            stream_blob(data, stream),
            stream.raw_size,
            sink,
            options);

        if (stats.output_bytes != 0 && stats.output_bytes != stream.raw_size) {
            throw std::runtime_error("backend reported inconsistent AUR2 directory output length");
        }
    }

    for (const auto& entry : entries) {
        const auto target = safe_archive_target(output_directory, entry.path);
        if (entry.type == EntryType::Directory) {
            if (!std::filesystem::is_directory(target)) {
                throw std::runtime_error("AUR2 directory extraction verification failed");
            }
        } else {
            if (!std::filesystem::is_regular_file(target) ||
                std::filesystem::file_size(target) != entry.logical_size) {
                throw std::runtime_error("AUR2 file extraction verification failed");
            }
        }
    }
}

} // namespace kephir2::aur2
