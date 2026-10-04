#include "kephir2/aur2.hpp"

#include <cassert>
#include <stdexcept>
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

    const CodecDescriptor codec{
        kCodecKephir,
        2,
        0,
        2,
        0,
        0,
        ByteBuffer{}
    };

    const std::vector<StreamRecord> streams{
        {1, 0, 4, 7, kCodecKephir, 0},
        {2, 4, 3, 5, kCodecKephir, 0},
    };

    const auto stream_bytes = encode_stream_table(streams);
    assert(decode_stream_table(stream_bytes) == streams);

    const std::vector<FileEntry> entries{
        {1, EntryType::Directory, "empty-dir", 0, 0, 0, 0, 0},
        {2, EntryType::File, "a.bin", 7, 1, 0, 0, 0},
        {3, EntryType::File, "nested/b.bin", 5, 2, 0, 0, 0},
        {4, EntryType::File, "empty.dat", 0, 0, 0, 0, 0},
    };

    Header header;
    header.logical_size = 12;
    header.feature_flags =
        feature_bit(Feature::Directory) |
        feature_bit(Feature::MultiStream) |
        feature_bit(Feature::Kephir2);

    const std::vector<Section> sections{
        {static_cast<std::uint32_t>(SectionType::FileTable),
         SectionFlagRequired,
         encode_file_table(entries)},
        {static_cast<std::uint32_t>(SectionType::CodecDescriptor),
         SectionFlagRequired,
         encode_codec_descriptor(codec)},
        {static_cast<std::uint32_t>(SectionType::BlockTable),
         SectionFlagRequired,
         stream_bytes},
        {static_cast<std::uint32_t>(SectionType::Data),
         SectionFlagRequired,
         ByteBuffer{1, 2, 3, 4, 5, 6, 7}},
    };

    const auto bytes = encode_container(header, sections);
    const auto container = decode_container(bytes);
    validate_container_structure(container);

    auto bad_logical = container;
    bad_logical.header.logical_size = 11;
    assert(throws_runtime([&] { validate_container_structure(bad_logical); }));

    auto missing_kephir_flag = container;
    missing_kephir_flag.header.feature_flags &= ~feature_bit(Feature::Kephir2);
    assert(throws_runtime([&] { validate_container_structure(missing_kephir_flag); }));

    auto missing_multistream_flag = container;
    missing_multistream_flag.header.feature_flags &= ~feature_bit(Feature::MultiStream);
    assert(throws_runtime([&] { validate_container_structure(missing_multistream_flag); }));

    auto missing_directory_flag = container;
    missing_directory_flag.header.feature_flags &= ~feature_bit(Feature::Directory);
    assert(throws_runtime([&] { validate_container_structure(missing_directory_flag); }));

    auto short_data = container;
    short_data.sections[3].payload.pop_back();
    assert(throws_runtime([&] { validate_container_structure(short_data); }));

    auto wrong_codec_streams = streams;
    wrong_codec_streams[0].codec_id = make_fourcc('T', 'E', 'S', 'T');
    auto wrong_codec = container;
    wrong_codec.sections[2].payload = encode_stream_table(wrong_codec_streams);
    assert(throws_runtime([&] { validate_container_structure(wrong_codec); }));

    auto gap_streams = streams;
    gap_streams[1].payload_offset = 5;
    auto gap = container;
    gap.sections[2].payload = encode_stream_table(gap_streams);
    assert(throws_runtime([&] { validate_container_structure(gap); }));

    auto bad_entries = entries;
    bad_entries[1].stream_offset = 1;
    auto out_of_range = container;
    out_of_range.sections[0].payload = encode_file_table(bad_entries);
    assert(throws_runtime([&] { validate_container_structure(out_of_range); }));

    const std::vector<StreamRecord> duplicate_streams{
        {1, 0, 1, 1, kCodecKephir, 0},
        {1, 1, 1, 1, kCodecKephir, 0},
    };
    assert(throws_runtime([&] { (void)encode_stream_table(duplicate_streams); }));

    const std::vector<StreamRecord> zero_stream{
        {0, 0, 1, 1, kCodecKephir, 0},
    };
    assert(throws_runtime([&] { (void)encode_stream_table(zero_stream); }));

    return 0;
}
