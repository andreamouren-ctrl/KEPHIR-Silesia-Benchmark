#include "AuroraVideoMotion.h"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace aurora::media;

namespace {

Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t phase) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes out(ys+2*us);

    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            out[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+phase*7u+((x/32u+phase)%11u)*9u+
                 ((y/24u+phase)%7u)*5u)&255u);

    for(std::uint32_t y=0;y<h/2;++y)
        for(std::uint32_t x=0;x<w/2;++x) {
            const auto i=static_cast<std::size_t>(y)*(w/2)+x;
            out[ys+i]=static_cast<Byte>((91u+x*2u+y+phase*3u)&255u);
            out[ys+us+i]=static_cast<Byte>((167u+x+y*3u+phase*5u)&255u);
        }
    return out;
}

Bytes extract_region(ByteView frame,
                     std::uint32_t fw,std::uint32_t fh,
                     std::uint32_t rx,std::uint32_t ry,
                     std::uint32_t rw,std::uint32_t rh) {
    const std::size_t fys=static_cast<std::size_t>(fw)*fh;
    const std::size_t fus=static_cast<std::size_t>(fw/2)*(fh/2);
    const std::size_t rys=static_cast<std::size_t>(rw)*rh;
    const std::size_t rus=static_cast<std::size_t>(rw/2)*(rh/2);
    Bytes out(rys+2*rus);

    for(std::uint32_t y=0;y<rh;++y) {
        const auto src=static_cast<std::size_t>(ry+y)*fw+rx;
        const auto dst=static_cast<std::size_t>(y)*rw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),rw,
                    out.begin()+static_cast<std::ptrdiff_t>(dst));
    }

    const auto fcw=fw/2;
    const auto rcw=rw/2;
    for(std::uint32_t y=0;y<rh/2;++y) {
        const auto src=static_cast<std::size_t>(ry/2+y)*fcw+rx/2;
        const auto dst=static_cast<std::size_t>(y)*rcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(fys+src),rcw,
                    out.begin()+static_cast<std::ptrdiff_t>(rys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(fys+fus+src),rcw,
                    out.begin()+static_cast<std::ptrdiff_t>(rys+rus+dst));
    }
    return out;
}

void verify(const char* name,
            ByteView cur,ByteView prev,
            std::uint32_t fw,std::uint32_t fh,
            std::uint32_t rx,std::uint32_t ry,
            std::uint32_t rw,std::uint32_t rh) {
    const auto cur_tile=extract_region(cur,fw,fh,rx,ry,rw,rh);
    const auto prev_tile=extract_region(prev,fw,fh,rx,ry,rw,rh);

    const auto legacy=AuroraVideoMotion::encode_mc8r4_adaptive(
        cur_tile,prev_tile,rw,rh,4.0,9);
    const auto direct=AuroraVideoMotion::encode_mc8r4_region_adaptive(
        cur,prev,fw,fh,rx,ry,rw,rh,4.0,9);

    if(legacy.motion_map!=direct.motion_map)
        throw std::runtime_error(std::string(name)+": motion map mismatch");
    if(legacy.residual_yuv420!=direct.residual_yuv420)
        throw std::runtime_error(std::string(name)+": residual mismatch");

    const auto legacy_dec=AuroraVideoMotion::decode_mc8r4(
        legacy.motion_map,legacy.residual_yuv420,prev_tile,rw,rh);
    const auto direct_dec=AuroraVideoMotion::decode_mc8r4_region(
        direct.motion_map,direct.residual_yuv420,prev,
        fw,fh,rx,ry,rw,rh);

    if(legacy_dec!=direct_dec)
        throw std::runtime_error(std::string(name)+": decode mismatch");
    if(legacy_dec!=cur_tile)
        throw std::runtime_error(std::string(name)+": lossless reconstruction failed");

    const auto legacy_mad=AuroraVideoMotion::sparse_luma_mad(
        cur_tile,prev_tile,rw,rh,8);
    const auto direct_mad=AuroraVideoMotion::sparse_luma_mad_region(
        cur,prev,fw,fh,rx,ry,rw,rh,8);
    if(legacy_mad!=direct_mad)
        throw std::runtime_error(std::string(name)+": activity mismatch");
}

} // namespace

int main() {
    try {
        constexpr std::uint32_t fw=768,fh=480;
        const auto prev=make_frame(fw,fh,0);
        const auto cur=make_frame(fw,fh,1);

        verify("top-left",cur,prev,fw,fh,0,0,256,240);
        verify("top-middle",cur,prev,fw,fh,256,0,256,240);
        verify("bottom-middle",cur,prev,fw,fh,256,240,256,240);
        verify("bottom-right",cur,prev,fw,fh,512,240,256,240);
        verify("subregion",cur,prev,fw,fh,128,120,128,120);

        std::cout<<"AURORA_ZERO_COPY_MOTION_EQUIVALENCE_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
