#include "AuroraVideoMotion.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace aurora::media;

static Bytes read_file(const std::string& path) {
    std::ifstream f(path,std::ios::binary);
    if(!f) throw std::runtime_error("cannot open "+path);
    f.seekg(0,std::ios::end);
    const auto n=f.tellg();
    f.seekg(0,std::ios::beg);
    Bytes out(static_cast<std::size_t>(n));
    if(!out.empty()) f.read(reinterpret_cast<char*>(out.data()),n);
    if(!f) throw std::runtime_error("cannot read "+path);
    return out;
}

static std::uint64_t fnv1a(ByteView data) {
    std::uint64_t h=1469598103934665603ull;
    for(const auto b:data) {
        h^=static_cast<std::uint64_t>(b);
        h*=1099511628211ull;
    }
    return h;
}

int main(int argc,char** argv) {
    try {
        if(argc!=2)
            throw std::runtime_error("usage: test_aurora_video_h3_conformance <vector_dir>");

        const std::string root=argv[1];
        constexpr std::uint32_t w=128,h=96;

        const auto prev=read_file(root+"/previous.yuv");
        const auto cur=read_file(root+"/current.yuv");
        const auto expected_motion=read_file(root+"/motion.bin");
        const auto expected_floor=read_file(root+"/residual_floor.bin");
        const auto expected_trunc=read_file(root+"/residual_trunc.bin");

        const auto dense=AuroraVideoMotion::dense_candidates(4);
        if(dense.size()!=81)
            throw std::runtime_error("dense candidate count");

        const auto floor=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Floor);
        const auto trunc=AuroraVideoMotion::encode_mc8r4_h3(
            cur,prev,w,h,DenseChromaPolicy::Trunc);

        if(floor.motion_map!=expected_motion)
            throw std::runtime_error("Python/C++ H3 motion-map mismatch");
        if(trunc.motion_map!=expected_motion)
            throw std::runtime_error("Python/C++ H3 trunc motion-map mismatch");
        if(floor.residual_yuv420!=expected_floor)
            throw std::runtime_error("Python/C++ H3 FLOOR residual mismatch");
        if(trunc.residual_yuv420!=expected_trunc)
            throw std::runtime_error("Python/C++ H3 TRUNC residual mismatch");

        const auto floor_dec=AuroraVideoMotion::decode_mc8r4_dense(
            floor.motion_map,floor.residual_yuv420,prev,w,h,DenseChromaPolicy::Floor);
        const auto trunc_dec=AuroraVideoMotion::decode_mc8r4_dense(
            trunc.motion_map,trunc.residual_yuv420,prev,w,h,DenseChromaPolicy::Trunc);

        if(floor_dec!=cur)
            throw std::runtime_error("H3 FLOOR roundtrip mismatch");
        if(trunc_dec!=cur)
            throw std::runtime_error("H3 TRUNC roundtrip mismatch");

        std::size_t odd=0;
        for(const auto idx:floor.motion_map) {
            if(idx>=dense.size())
                throw std::runtime_error("bad dense index in H3 map");
            const auto [dx,dy]=dense[idx];
            if((dx&1)||(dy&1)) ++odd;
        }

        std::cout<<"AURORA_NATIVE_H3_CONFORMANCE_PASS"
                 <<" blocks="<<floor.motion_map.size()
                 <<" odd_blocks="<<odd
                 <<" motion_fp="<<fnv1a(floor.motion_map)
                 <<" floor_fp="<<fnv1a(floor.residual_yuv420)
                 <<" trunc_fp="<<fnv1a(trunc.residual_yuv420)
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
