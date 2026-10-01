#include "kephir2/aur2.hpp"

#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

template <class F>
bool throws_runtime(F&& fn) {
    try {
        fn();
        return false;
    } catch (const std::runtime_error&) {
        return true;
    }
}

} // namespace

int main() {
    using namespace kephir2;
    using namespace kephir2::aur2;

    static_assert(kFixedHeaderSize == 64);
    static_assert(kSectionHeaderSize == 16);
    static_assert(kCodecKephir == make_fourcc('K', 'P', 'H', 'R'));

    assert(is_safe_relative_path("file.txt"));
    assert(is_safe_relative_path("docs/source/main.cpp"));
    assert(!is_safe_relative_path(""));
    assert(!is_safe_relative_path("/absolute"));
    assert(!is_safe_relative_path("../escape"));
    assert(!is_safe_relative_path("a/../escape"));
    assert(!is_safe_relative_path("a//b"));
    assert(!is_safe_relative_path("a\\b"));
    assert(!is_safe_relative_path("C:/absolute"));

    Header header;
    header.feature_flags =
        feature_bit(Feature::Directory) |
        feature_bit(Feature::MultiStream) |
        feature_bit(Feature::Integrity) |
        feature_bit(Feature::Kephir2);
    header.archive_id = 0x1122334455667788ull;
    header.logical_size = 0x1'0000'0100ull;

    const auto header_bytes = encode_header(header);
    assert(header_bytes.size() == 64);
    assert(header_bytes[0] == 'A');
    assert(header_bytes[1] == 'U');
    assert(header_bytes[2] == 'R');
    assert(header_bytes[3] == '2');

    const auto decoded_header = decode_header(header_bytes);
    assert(decoded_header.container_major == 2);
    assert(decoded_header.container_minor == 0);
    assert(decoded_header.header_size == 64);
    assert(decoded_header.archive_id == header.archive_id);
    assert(decoded_header.logical_size == header.logical_size);
    assert(decoded_header.feature_flags == header.feature_flags);
    assert(decoded_header.header_crc32 != 0);

    auto corrupted_header = header_bytes;
    corrupted_header[24] ^= 0x01;
    assert(throws_runtime([&] { (void)decode_header(corrupted_header); }));

    auto wrong_magic = header_bytes;
    wrong_magic[0] = 'X';
    assert(throws_runtime([&] { (void)decode_header(wrong_magic); }));

    CodecDescriptor codec;
    codec.codec_id = kCodecKephir;
    codec.codec_major = 2;
    codec.codec_minor = 3;
    codec.minimum_decoder_major = 2;
    codec.minimum_decoder_minor = 1;
    codec.codec_flags = 0x55aa;
    codec.private_data = ByteBuffer{0x10, 0x20, 0x30, 0x40};

    const auto codec_bytes = encode_codec_descriptor(codec);
    assert(decode_codec_descriptor(codec_bytes) == codec);

    auto codec_trailing = codec_bytes;
    codec_trailing.push_back(0);
    assert(throws_runtime([&] { (void)decode_codec_descriptor(codec_trailing); }));

    const std::string micro = std::string("docs/") + "\xc2\xb5" + ".txt";
    const std::vector<FileEntry> entries{
        {1, EntryType::Directory, "empty", 0, 0, 0, 0x10, 1'700'000'000'000'000'000ll},
        {2, EntryType::File, "docs/readme.txt", 1234, 7, 0, 0x20, 1'700'000'001'000'000'000ll},
        {3, EntryType::File, micro, 0x1'0000'0000ull, 8, 4096, 0, -1},
    };

    const auto table_bytes = encode_file_table(entries);
    const auto decoded_entries = decode_file_table(table_bytes);
    assert(decoded_entries == entries);

    auto table_trailing = table_bytes;
    table_trailing.push_back(0);
    assert(throws_runtime([&] { (void)decode_file_table(table_trailing); }));

    const std::vector<FileEntry> duplicate_id{
        {1, EntryType::File, "a", 1, 0, 0, 0, 0},
        {1, EntryType::File, "b", 1, 0, 0, 0, 0},
    };
    assert(throws_runtime([&] { (void)encode_file_table(duplicate_id); }));

    const std::vector<FileEntry> duplicate_path{
        {1, EntryType::File, "same", 1, 0, 0, 0, 0},
        {2, EntryType::File, "same", 1, 0, 0, 0, 0},
    };
    assert(throws_runtime([&] { (void)encode_file_table(duplicate_path); }));

    const std::vector<FileEntry> unsafe_path{
        {1, EntryType::File, "../escape", 1, 0, 0, 0, 0},
    };
    assert(throws_runtime([&] { (void)encode_file_table(unsafe_path); }));

    const std::vector<FileEntry> bad_directory{
        {1, EntryType::Directory, "dir", 1, 0, 0, 0, 0},
    };
    assert(throws_runtime([&] { (void)encode_file_table(bad_directory); }));

    Section file_table_section{
        static_cast<std::uint32_t>(SectionType::FileTable),
        SectionFlagRequired,
        table_bytes,
    };
    Section codec_section{
        static_cast<std::uint32_t>(SectionType::CodecDescriptor),
        SectionFlagRequired,
        codec_bytes,
    };
    Section data_section{
        static_cast<std::uint32_t>(SectionType::Data),
        SectionFlagRequired,
        ByteBuffer{0xde, 0xad, 0xbe, 0xef},
    };
    Section future_ignorable{
        0x8000'0001u,
        SectionFlagIgnorable,
        ByteBuffer{1, 2, 3},
    };

    const std::vector<Section> sections{
        file_table_section,
        codec_section,
        data_section,
        future_ignorable,
    };

    const auto archive = encode_container(header, sections);
    const auto decoded = decode_container(archive);

    assert(decoded.header.container_major == 2);
    assert(decoded.header.toc_offset == 64);
    assert(decoded.header.footer_offset == 0);
    assert(decoded.header.logical_size == header.logical_size);
    assert(decoded.sections == sections);
    assert(decode_file_table(decoded.sections[0].payload) == entries);
    assert(decode_codec_descriptor(decoded.sections[1].payload) == codec);

    auto truncated = archive;
    truncated.pop_back();
    assert(throws_runtime([&] { (void)decode_container(truncated); }));

    const std::vector<Section> unknown_required{
        {0x8000'0002u, SectionFlagRequired, ByteBuffer{0x01}},
    };
    assert(throws_runtime([&] { (void)encode_container(header, unknown_required); }));

    const std::vector<Section> contradictory_flags{
        {static_cast<std::uint32_t>(SectionType::Data),
         SectionFlagIgnorable | SectionFlagRequired,
         ByteBuffer{0x01}},
    };
    assert(throws_runtime([&] { (void)encode_container(header, contradictory_flags); }));

    const std::vector<Section> no_sections;
    const auto empty_container_bytes = encode_container(Header{}, no_sections);
    const auto empty_container = decode_container(empty_container_bytes);
    assert(empty_container.sections.empty());
    assert(empty_container.header.toc_offset == 0);

    return 0;
}
