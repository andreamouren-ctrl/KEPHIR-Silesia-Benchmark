#pragma once

#include <filesystem>

namespace kephir2::aur2 {

// Finalizes a base AUR2 file without materializing its DATA section. The output
// receives source filesystem metadata, a rebuilt SEEK_INDEX and FTR1 footer.
// Unchanged section payloads are copied in bounded chunks from base_archive.
void finalize_archive_file_backed(
    const std::filesystem::path& base_archive,
    const std::filesystem::path& source,
    const std::filesystem::path& output_archive);

} // namespace kephir2::aur2
