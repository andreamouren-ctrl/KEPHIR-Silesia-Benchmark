#include "AuroraKhepriExp37MemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoResidual.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes make_frame(std::uint32_t w,std::uint32_t h,int shift) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((x*3+y*5+shift)&255);
    for(std::size_t i=0;i<us;++i) {
        b[ys+i]=static_cast<Byte>((80+(i%53)+shift)&255);
        b[ys+us+i]=static_cast<Byte>((170+(i%71)+shift)&255);
    }
    return b;
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        const auto prev=make_frame(w,h,0);
        const auto cur=make_frame(w,h,2);

        const auto motion=AuroraVideoMotion::encode_mc8r4(cur,prev,w,h);
        const auto mode=AuroraVideoResidual::choose_mode(motion.residual_yuv420);
        const auto mapped=AuroraVideoResidual::map(motion.residual_yuv420,mode);

        AuroraKhepriExp37MemoryAdapter khepri;
        const auto packed=khepri.encode(mapped);
        const auto unpacked=khepri.decode(packed);
        const auto residual=AuroraVideoResidual::unmap(unpacked,mode);
        const auto reconstructed=AuroraVideoMotion::decode_mc8r4(
            motion.motion_map,residual,prev,w,h);

        if(reconstructed!=cur)
            throw std::runtime_error("native video pipeline roundtrip failed");

        std::cout<<"NATIVE_VIDEO_PIPELINE_PASS raw_residual="<<motion.residual_yuv420.size()
                 <<" khepri_frame="<<packed.size()
                 <<" motion_map="<<motion.motion_map.size()<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
