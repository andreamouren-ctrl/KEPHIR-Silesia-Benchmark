#include "AuroraVideoCompute.h"
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

static Bytes frame(std::uint32_t w,std::uint32_t h,std::uint32_t shift) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x)
            b[static_cast<std::size_t>(y)*w+x]
                = static_cast<Byte>((3u*x+5u*y+shift+((x/32u)%5u)*7u)&255u);
    for(std::size_t i=0;i<us;++i) {
        b[ys+i]=static_cast<Byte>((80u+i+shift)&255u);
        b[ys+us+i]=static_cast<Byte>((160u+3u*i+shift)&255u);
    }
    return b;
}

struct Result {
    double seconds{};
    std::size_t bytes{};
};

static Result run_pipeline(IVideoMotionCompute& c,
                           const Bytes& cur,const Bytes& prev,
                           std::uint32_t w,std::uint32_t h,
                           int iterations) {
    std::size_t bytes=0;
    auto t0=Clock::now();
    for(int i=0;i<iterations;++i) {
        const auto motion=c.motion_map_mc8r4(cur,prev,w,h);
        const auto residual=c.residual_yuv420_mc8r4(cur,prev,motion,w,h);
        const auto reconstructed=c.reconstruct_yuv420_mc8r4(prev,residual,motion,w,h);
        if(reconstructed!=cur)
            throw std::runtime_error("pipeline reconstruction mismatch");
        bytes+=cur.size();
    }
    const auto t1=Clock::now();
    return {std::chrono::duration<double>(t1-t0).count(),bytes};
}

int main() {
    try {
        constexpr std::uint32_t w=256,h=240;
        constexpr int warmup=2;
        constexpr int iterations=10;
        constexpr double fps_target=30.0;
        const auto prev=frame(w,h,0);
        const auto cur=frame(w,h,3);

        auto cpu=make_cpu_video_motion_compute();
        auto d3d=make_d3d12_video_motion_compute(false);

        for(int i=0;i<warmup;++i) {
            auto m=cpu->motion_map_mc8r4(cur,prev,w,h);
            auto r=cpu->residual_yuv420_mc8r4(cur,prev,m,w,h);
            if(cpu->reconstruct_yuv420_mc8r4(prev,r,m,w,h)!=cur)
                throw std::runtime_error("CPU warmup mismatch");

            m=d3d->motion_map_mc8r4(cur,prev,w,h);
            r=d3d->residual_yuv420_mc8r4(cur,prev,m,w,h);
            if(d3d->reconstruct_yuv420_mc8r4(prev,r,m,w,h)!=cur)
                throw std::runtime_error("D3D12 warmup mismatch");
        }

        const auto cr=run_pipeline(*cpu,cur,prev,w,h,iterations);
        const auto gr=run_pipeline(*d3d,cur,prev,w,h,iterations);
        const auto caps=d3d->capabilities();

        const double cpu_fps=iterations/cr.seconds;
        const double d3d_fps=iterations/gr.seconds;
        const double cpu_mbps=(cr.bytes/(1024.0*1024.0))/cr.seconds;
        const double d3d_mbps=(gr.bytes/(1024.0*1024.0))/gr.seconds;
        const double speedup=cr.seconds/gr.seconds;
        const double cpu_rt=cpu_fps/fps_target;
        const double d3d_rt=d3d_fps/fps_target;

        std::cout<<std::fixed<<std::setprecision(3)
                 <<"AURORA_CPU_D3D12_PIPELINE_BENCH"
                 <<" width="<<w<<" height="<<h
                 <<" iterations="<<iterations
                 <<" frame_bytes="<<cur.size()
                 <<" cpu_seconds="<<cr.seconds
                 <<" d3d12_seconds="<<gr.seconds
                 <<" cpu_fps="<<cpu_fps
                 <<" d3d12_fps="<<d3d_fps
                 <<" cpu_mib_s="<<cpu_mbps
                 <<" d3d12_mib_s="<<d3d_mbps
                 <<" speedup_x="<<speedup
                 <<" cpu_realtime_30fps_x="<<cpu_rt
                 <<" d3d12_realtime_30fps_x="<<d3d_rt
                 <<" hardware="<<(caps.hardware_accelerated?1:0)
                 <<" adapter=\""<<caps.adapter_name<<"\""
                 <<" mismatches=0\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
