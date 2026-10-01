#pragma once

#include "kephir2/aur2.hpp"
#include "kephir2/aur2_seek.hpp"

#include <cstdint>
#include <filesystem>
#include <vector>

namespace kephir2::aur2 {

// File-backed AUR2 reader for indexed archives. Construction validates the
// SEEK_INDEX/layout but never materializes DATA. Payload bytes are fetched only
// when a caller explicitly requests a section or bounded range.
class IndexedRangeReader {
public:
    explicit IndexedRangeReader(std::filesystem::path archive);

    [[nodiscard]] const Header& header() const noexcept { return header_; }
    [[nodiscard]] std::uint64_t archive_size() const noexcept { return archive_size_; }
    [[nodiscard]] const std::vector<SeekIndexRecord>& records() const noexcept {
        return records_;
    }

    [[nodiscard]] const SeekIndexRecord& require_section(SectionType type) const;

    [[nodiscard]] ByteBuffer read_section_payload(SectionType type) const;

    [[nodiscard]] ByteBuffer read_section_range(
        SectionType type,
        std::uint64_t relative_offset,
        std::uint64_t size) const;

private:
    std::filesystem::path archive_;
    Header header_{};
    std::uint64_t archive_size_{0};
    std::vector<SeekIndexRecord> records_;
};

} // namespace kephir2::aur2
