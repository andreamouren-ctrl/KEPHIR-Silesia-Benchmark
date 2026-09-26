#include "kephir2/native37_blob.hpp"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> repeated(
    const std::string& pattern,
    std::size_t size) {
    std::vector<std::uint8_t> out;
    out.reserve(size);
    while(out.size()<size){
        const auto n=std::min(pattern.size(),size-out.size());
        out.insert(out.end(),pattern.begin(),pattern.begin()+n);
    }
    return out;
}

std::vector<std::uint8_t> noise(std::size_t size){
    std::vector<std::uint8_t> out(size);
    std::uint32_t x=0x9e3779b9u;
    for(auto& b:out){
        x^=x<<13; x^=x>>17; x^=x<<5;
        b=static_cast<std::uint8_t>(x&0xffu);
    }
    return out;
}

void check(const std::vector<std::uint8_t>& raw){
    const auto blob=kephir2::native37::encode_aur2_blob(raw);
    const auto dec=kephir2::native37::decode_aur2_blob(blob);
    assert(dec==raw);
}

} // namespace

int main(){
    check({});
    check({0});
    check(std::vector<std::uint8_t>(4096,0));
    check(repeated("int main(){return 0;}\n",128u*1024u));
    check(repeated("ordinary prose words and spaces. ",512u*1024u));
    check(noise(512u*1024u));
    check(noise(512u*1024u+12345u));
    return 0;
}
