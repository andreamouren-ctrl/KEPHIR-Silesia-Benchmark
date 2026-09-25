#include "AuroraKhepriFastDMemoryAdapter.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

int main() {
    try {
        AuroraKhepriFastDMemoryAdapter backend;
        Bytes input(128 * 1024);
        for(std::size_t i=0;i<input.size();++i) {
            const auto lane=(i/257u)&7u;
            input[i]=static_cast<Byte>((i*13u + lane*29u + (i>>8)) & 255u);
        }

        const auto packed=backend.encode(input);
        const auto decoded=backend.decode(packed);
        if(decoded!=input)
            throw std::runtime_error("FAST-D video profile roundtrip mismatch");

        std::cout<<"FAST_D_VIDEO_PROFILE_ROUNDTRIP_PASS"
                 <<" raw_bytes="<<input.size()
                 <<" packed_bytes="<<packed.size()
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
