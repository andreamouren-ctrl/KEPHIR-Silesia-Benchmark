#include "AuroraVideoResidual.h"
#include "AuroraVideoTileCodec.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

int main() {
    try {
        const Bytes src{0,1,255,2,254,3,253,127,128,200,56};

        const auto zz = AuroraVideoResidual::map(src,VideoResidualMode::ZigZagInter);
        const auto back = AuroraVideoResidual::unmap(zz,VideoResidualMode::ZigZagInter);
        if(back != src) throw std::runtime_error("zigzag roundtrip");

        for(unsigned i=0;i<256;++i) {
            const auto b=static_cast<Byte>(i);
            if(AuroraVideoResidual::unzigzag_byte(AuroraVideoResidual::zigzag_byte(b))!=b)
                throw std::runtime_error("byte mapping mismatch");
        }

        const Bytes low{0,1,255,1,255,2,254,0,0,1,255};
        const Bytes high{0,64,128,192,32,224,96,160};

        if(AuroraVideoResidual::choose_mode(low)!=VideoResidualMode::ZigZagInter)
            throw std::runtime_error("low residual mode");
        if(AuroraVideoResidual::choose_mode(high)!=VideoResidualMode::Mod8)
            throw std::runtime_error("high residual mode");

        AuroraVideoTileCodec codec;
        auto packet=codec.encode_residual(low);
        if(packet.mode!=VideoResidualMode::ZigZagInter)
            throw std::runtime_error("tile codec mode");
        if(codec.decode_residual(packet)!=low)
            throw std::runtime_error("tile codec roundtrip");

        std::cout<<"VIDEO_RESIDUAL_CPP_PASS mean_low="
                 <<AuroraVideoResidual::mean_signed_magnitude(low)<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
