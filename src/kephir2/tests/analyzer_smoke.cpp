#include "kephir2/analyzer.hpp"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

int main() {
    using namespace kephir2;

    ContentAnalyzer analyzer;

    const std::string prose =
        "This is a deterministic prose sample with ordinary English words and spaces. "
        "It is deliberately repeated so the content is clearly textual rather than binary. ";
    std::vector<std::uint8_t> prose_bytes;
    for (int i = 0; i < 8; ++i) {
        prose_bytes.insert(prose_bytes.end(), prose.begin(), prose.end());
    }
    const auto prose_result = analyzer.analyze_bytes(prose_bytes);
    assert(prose_result.content_class == ContentClass::TextProse
        || prose_result.content_class == ContentClass::EncodedText
        || prose_result.content_class == ContentClass::TextGeneric);

    std::vector<std::uint8_t> zeros(4096, 0);
    const auto zero_result = analyzer.analyze_bytes(zeros);
    assert(zero_result.content_class == ContentClass::BinaryZero);
    assert(zero_result.metrics.zero_fraction == 1.0);

    const std::string code =
        "int main(){for(int i=0;i<100;++i){value[i]=i*i;}}\n"
        "struct Node{int x;int y;};\n";
    std::vector<std::uint8_t> code_bytes;
    for (int i = 0; i < 16; ++i) {
        code_bytes.insert(code_bytes.end(), code.begin(), code.end());
    }
    const auto code_result = analyzer.analyze_bytes(code_bytes);
    assert(code_result.content_class == ContentClass::TextCode);

    const auto tmp = std::filesystem::temp_directory_path() / "kephir2_analyzer_smoke";
    std::filesystem::remove_all(tmp);
    std::filesystem::create_directories(tmp / "sub");

    {
        std::ofstream f(tmp / "a.txt", std::ios::binary);
        f.write(reinterpret_cast<const char*>(prose_bytes.data()),
                static_cast<std::streamsize>(prose_bytes.size()));
    }
    {
        std::ofstream f(tmp / "sub" / "b.bin", std::ios::binary);
        f.write(reinterpret_cast<const char*>(zeros.data()),
                static_cast<std::streamsize>(zeros.size()));
    }
    {
        std::ofstream f(tmp / "sub" / "c.cpp", std::ios::binary);
        f.write(reinterpret_cast<const char*>(code_bytes.data()),
                static_cast<std::streamsize>(code_bytes.size()));
    }

    const auto features = analyzer.analyze_directory(tmp);
    assert(features.file_count == 3);
    assert(features.logical_bytes ==
        prose_bytes.size() + zeros.size() + code_bytes.size());
    assert(features.sampled_content_groups >= 2);
    assert(features.sampled_dominant_file_fraction > 0.0);
    assert(features.sampled_dominant_file_fraction <= 1.0);
    assert(features.sampled_dominant_byte_fraction > 0.0);
    assert(features.sampled_dominant_byte_fraction <= 1.0);
    assert(features.sampled_entropy >= 0.0);
    assert(features.sampled_entropy <= 8.0);

    std::filesystem::remove_all(tmp);
    return 0;
}
