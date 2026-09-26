#include "kephir2/packing.hpp"

#include <array>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string>

namespace {

std::string hex(const kephir2::ByteBuffer& data) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out;
    out.reserve(data.size() * 2);
    for (const auto b : data) {
        out.push_back(digits[(b >> 4) & 0x0f]);
        out.push_back(digits[b & 0x0f]);
    }
    return out;
}

std::uint64_t fnv1a_group(
    const kephir2::PackedGroupSource& source) {

    std::uint64_t hash = 1469598103934665603ull;
    std::array<std::uint8_t, 4093> buffer{};
    std::uint64_t offset = 0;

    while (offset < source.size()) {
        const auto got = source.read(offset, buffer);
        if (got == 0) {
            break;
        }
        for (std::size_t i = 0; i < got; ++i) {
            hash ^= buffer[i];
            hash *= 1099511628211ull;
        }
        offset += got;
    }

    if (offset != source.size()) {
        throw std::runtime_error("group source hash short read");
    }
    return hash;
}

} // namespace

int main(int argc, char** argv) {
    using namespace kephir2;

    if (argc != 2) {
        std::cerr << "usage: kephir2_packing_dump DIRECTORY\n";
        return 2;
    }

    try {
        const std::filesystem::path root(argv[1]);
        ContentAnalyzer analyzer;
        const auto plan = build_directory_packing_plan(root, analyzer);

        std::cout << "MANIFEST_HEX\t" << hex(plan.manifest) << '\n';

        for (std::size_t i = 0; i < plan.groups.size(); ++i) {
            const auto& g = plan.groups[i];
            PackedGroupSource source(root, plan, i);
            std::cout
                << "GROUP\t" << i << '\t'
                << g.name << '\t'
                << g.raw_length << '\t'
                << fnv1a_group(source) << '\n';
        }

        for (const auto& f : plan.files) {
            std::cout
                << "FILE\t"
                << f.path << '\t'
                << to_string(f.content_class) << '\t'
                << f.group_name << '\t'
                << f.group_id << '\t'
                << f.size << '\t'
                << f.group_offset << '\n';
        }

        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
