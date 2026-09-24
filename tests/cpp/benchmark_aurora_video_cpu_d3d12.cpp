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
    double motion_seconds{};
    double residual_seconds{};
    double reconstruct_seconds{};
    std::size_t bytes{};
};

static Result run_pipeline(IVideoMotionCompute& c,
                           const Bytes& cur,const Bytes& prev,
                           std::uint32_t w,std::uint32_t h,
                           int iterations) {
    std::size_t bytes=0;
    double motion_seconds=0.0;
    double residual_seconds=0.0;
    double reconstruct_seconds=0.0;
    for(int i=0;i<iterations;++i) {
        const auto motion_begin=Clock::now();
        const auto motion=c.motion_map_mc8r4(cur,prev,w,h);
        const auto motion_end=Clock::now();
        const auto residual=c.residual_yuv420_mc8r4(cur,prev,motion,w,h);
        const auto residual_end=Clock::now();
        const auto reconstructed=c.reconstruct_yuv420_mc8r4(prev,residual,motion,w,h);
        const auto reconstruct_end=Clock::now();
        if(reconstructed!=cur)
            throw std::runtime_error("pipeline reconstruction mismatch");
        motion_seconds+=std::chrono::duration<double>(motion_end-motion_begin).count();
        residual_seconds+=std::chrono::duration<double>(residual_end-motion_end).count();
        reconstruct_seconds+=std::chrono::duration<double>(reconstruct_end-residual_end).count();
        bytes+=cur.size();
    }
    return {motion_seconds,residual_seconds,reconstruct_seconds,bytes};
}

int main() {
    try {
        constexpr std::uint32_t w=3840,h=2160;
        constexpr int warmup=1;
        constexpr int iterations=3;
        constexpr double fps_target=60.0;
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

        const double cpu_encode=cr.motion_seconds+cr.residual_seconds;
        const double d3d_encode=gr.motion_seconds+gr.residual_seconds;
        const double cpu_total=cpu_encode+cr.reconstruct_seconds;
        const double d3d_total=d3d_encode+gr.reconstruct_seconds;
        const double cpu_fps=iterations/cpu_total;
        const double d3d_fps=iterations/d3d_total;
        const double cpu_mbps=(cr.bytes/(1024.0*1024.0))/cpu_total;
        const double d3d_mbps=(gr.bytes/(1024.0*1024.0))/d3d_total;
        const double speedup=cpu_total/d3d_total;
        const double cpu_rt=cpu_fps/fps_target;
        const double d3d_rt=d3d_fps/fps_target;

        std::cout<<std::fixed<<std::setprecision(3)
                 <<"AURORA_CPU_D3D12_PIPELINE_BENCH"
                 <<" width="<<w<<" height="<<h
                 <<" iterations="<<iterations
                 <<" frame_bytes="<<cur.size()
                 <<" cpu_motion_ms="<<(cr.motion_seconds*1000.0/iterations)
                 <<" cpu_residual_ms="<<(cr.residual_seconds*1000.0/iterations)
                 <<" cpu_reconstruct_ms="<<(cr.reconstruct_seconds*1000.0/iterations)
                 <<" cpu_encode_ms="<<(cpu_encode*1000.0/iterations)
                 <<" cpu_decode_ms="<<(cr.reconstruct_seconds*1000.0/iterations)
                 <<" cpu_total_ms="<<(cpu_total*1000.0/iterations)
                 <<" d3d12_motion_ms="<<(gr.motion_seconds*1000.0/iterations)
                 <<" d3d12_residual_ms="<<(gr.residual_seconds*1000.0/iterations)
                 <<" d3d12_reconstruct_ms="<<(gr.reconstruct_seconds*1000.0/iterations)
                 <<" d3d12_encode_ms="<<(d3d_encode*1000.0/iterations)
                 <<" d3d12_decode_ms="<<(gr.reconstruct_seconds*1000.0/iterations)
                 <<" d3d12_total_ms="<<(d3d_total*1000.0/iterations)
                 <<" cpu_fps="<<cpu_fps
                 <<" d3d12_fps="<<d3d_fps
                 <<" cpu_mib_s="<<cpu_mbps
                 <<" d3d12_mib_s="<<d3d_mbps
                 <<" speedup_x="<<speedup
                 <<" cpu_realtime_60fps_x="<<cpu_rt
                 <<" d3d12_realtime_60fps_x="<<d3d_rt
                 <<" transfer_overhead=included_in_d3d12_end_to_end"
                 <<" hardware="<<(caps.hardware_accelerated?1:0)
                 <<" adapter=\""<<caps.adapter_name<<"\""
                 <<" mismatches=0\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
