#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace aurora::media;
using Clock=std::chrono::steady_clock;

extern "C" void aurora_fastd_runtime_set_depths(int,int);
extern "C" Bytes aurora_fastd_runtime_encode(ByteView);
extern "C" Bytes aurora_fastd_runtime_decode(ByteView);

struct ActionStats {
    std::uint64_t trials=0;
    double total_ms=0.0;
    std::uint64_t total_bytes=0;
};
struct ContextStats {
    std::array<ActionStats,3> a{};
};
struct EncTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    Bytes packed;
    std::uint8_t action=1;
    std::string key;
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi){
    const std::size_t ys=(std::size_t)w*h,us=(std::size_t)(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){
        auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;
        b[(std::size_t)y*w+x]=(Byte)((x*3u+y*5u+m*7u+fi*2u)&255u);
    }
    auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){
        auto i=(std::size_t)y*cw+x;
        b[ys+i]=(Byte)((80u+x+y+fi)&255u);
        b[ys+us+i]=(Byte)((170u+2u*x+y+fi*2u)&255u);
    }
    return b;
}
static Bytes extract_tile(ByteView f,const VideoTile&t){
    constexpr std::uint32_t fw=3840,fh=2160;
    const std::size_t ys=(std::size_t)fw*fh; auto cw=fw/2;
    const std::size_t us=(std::size_t)cw*(fh/2),tys=(std::size_t)t.width*t.height;
    auto tcw=t.width/2,tch=t.height/2; const std::size_t tus=(std::size_t)tcw*tch;
    Bytes o(tys+2*tus);
    for(std::uint32_t y=0;y<t.height;++y){
        auto s=(std::size_t)(t.y+y)*fw+t.x,d=(std::size_t)y*t.width;
        std::copy_n(f.begin()+(std::ptrdiff_t)s,t.width,o.begin()+(std::ptrdiff_t)d);
    }
    for(std::uint32_t y=0;y<tch;++y){
        auto s=(std::size_t)(t.y/2+y)*cw+t.x/2,d=(std::size_t)y*tcw;
        std::copy_n(f.begin()+(std::ptrdiff_t)(ys+s),tcw,o.begin()+(std::ptrdiff_t)(tys+d));
        std::copy_n(f.begin()+(std::ptrdiff_t)(ys+us+s),tcw,o.begin()+(std::ptrdiff_t)(tys+tus+d));
    }
    return o;
}
template<class F> static void parallel_for(std::size_t n,F fn){
    std::atomic<std::size_t> next{0}; std::vector<std::thread> pool;
    for(std::uint32_t w=0;w<4;++w) pool.emplace_back([&,w]{
        for(;;){auto i=next.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;fn(i,w);}
    });
    for(auto&t:pool)t.join();
}
static double entropy_sample(ByteView b){
    if(b.empty())return 0.0;
    std::array<std::uint32_t,256> c{}; std::uint64_t n=0;
    for(std::size_t i=0;i<b.size();i+=32){++c[b[i]];++n;}
    double h=0.0;
    for(auto v:c)if(v){double p=(double)v/(double)n;h-=p*std::log2(p);}
    return h;
}
static std::string context_key(ByteView b){
    const double h=entropy_sample(b);
    std::uint64_t z=0,n=0;
    for(std::size_t i=0;i<b.size();i+=32){z+=(b[i]==0);++n;}
    const double zp=n?(double)z/n:0.0;
    const double mag=AuroraVideoResidual::mean_signed_magnitude(b);
    int hb=std::min(7,std::max(0,(int)h));
    int zb=std::min(4,std::max(0,(int)(zp*10.0)));
    int mb=std::min(7,std::max(0,(int)(mag/1.25)));
    return "h"+std::to_string(hb)+":z"+std::to_string(zb)+":m"+std::to_string(mb);
}
static void set_action(int a){
    if(a==0)aurora_fastd_runtime_set_depths(24,12);
    else if(a==1)aurora_fastd_runtime_set_depths(48,24);
    else aurora_fastd_runtime_set_depths(64,32);
}
static int choose_action(const std::map<std::string,ContextStats>&model,const std::string&key){
    auto it=model.find(key);
    if(it==model.end())return 1;
    const auto&s=it->second;
    std::array<double,3> bytes{},ms{};
    for(int a=0;a<3;++a){
        if(!s.a[a].trials)return 1;
        bytes[a]=(double)s.a[a].total_bytes/s.a[a].trials;
        ms[a]=s.a[a].total_ms/s.a[a].trials;
    }
    const double best=*std::min_element(bytes.begin(),bytes.end());
    // EXP71-media policy: prefer the shallowest action whose learned size
    // stays inside a very small local loss budget.
    if(bytes[0] <= best*1.0045) return 0;
    if(bytes[1] <= best*1.0020) return 1;
    return 2;
}
static double percentile(std::vector<double>v,double q){
    std::sort(v.begin(),v.end());double p=q*(v.size()-1);
    auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);
    return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);
}

struct Summary{
    std::vector<double>ms;
    std::vector<std::uint64_t>bytes;
    std::uint64_t a0=0,a1=0,a2=0;
};

static Summary run_fixed(int startFi,int count){
    auto cfg=video_profile_config(VideoProfile::Balanced);
    auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    auto prev=make_frame(3840,2160,startFi-1); Summary s;
    for(int fi=startFi;fi<startFi+count;++fi){
        auto cur=make_frame(3840,2160,fi); std::vector<EncTile> out(plan.tiles.size());
        auto t0=Clock::now();
        parallel_for(plan.tiles.size(),[&](std::size_t i,std::uint32_t){
            auto&t=plan.tiles[i];auto c=extract_tile(cur,t),p=extract_tile(prev,t);
            auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
            auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
            set_action(1);
            out[i]={t,std::move(mr.motion_map),mode,aurora_fastd_runtime_encode(mapped),1,{}};
        });
        auto t1=Clock::now();
        parallel_for(out.size(),[&](std::size_t i,std::uint32_t){
            auto mapped=aurora_fastd_runtime_decode(out[i].packed);
            auto res=AuroraVideoResidual::unmap(mapped,out[i].mode);
            auto p=extract_tile(prev,out[i].tile);
            auto rec=AuroraVideoMotion::decode_mc8r4(out[i].motion,res,p,out[i].tile.width,out[i].tile.height);
            if(rec!=extract_tile(cur,out[i].tile))throw std::runtime_error("fixed roundtrip");
        });
        std::uint64_t sz=0;for(auto&x:out)sz+=x.packed.size()+x.motion.size()+3;
        s.ms.push_back(std::chrono::duration<double,std::milli>(t1-t0).count());s.bytes.push_back(sz);s.a1+=out.size();
        prev=cur;
    }
    return s;
}

static void train_model(std::map<std::string,ContextStats>&model,int frames){
    auto cfg=video_profile_config(VideoProfile::Balanced);
    auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    auto prev=make_frame(3840,2160,0);
    std::mutex mu;
    for(int fi=1;fi<=frames;++fi){
        auto cur=make_frame(3840,2160,fi);
        parallel_for(plan.tiles.size(),[&](std::size_t i,std::uint32_t){
            // Sparse contextual exploration keeps training finite.
            if(((i+(std::size_t)fi)%3)!=0)return;
            auto&t=plan.tiles[i];auto c=extract_tile(cur,t),p=extract_tile(prev,t);
            auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
            auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
            const auto key=context_key(mapped);
            std::array<std::size_t,3> sizes{};
            std::array<double,3> times{};
            for(int a=0;a<3;++a){
                set_action(a);auto q0=Clock::now();auto pack=aurora_fastd_runtime_encode(mapped);auto q1=Clock::now();
                sizes[a]=pack.size();times[a]=std::chrono::duration<double,std::milli>(q1-q0).count();
                if(aurora_fastd_runtime_decode(pack)!=mapped)throw std::runtime_error("training roundtrip");
            }
            std::lock_guard<std::mutex>g(mu);
            auto&cs=model[key];
            for(int a=0;a<3;++a){cs.a[a].trials++;cs.a[a].total_bytes+=sizes[a];cs.a[a].total_ms+=times[a];}
        });
        prev=cur;
    }
}

static Summary run_learned(const std::map<std::string,ContextStats>&model,int startFi,int count){
    auto cfg=video_profile_config(VideoProfile::Balanced);
    auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    auto prev=make_frame(3840,2160,startFi-1); Summary s;
    for(int fi=startFi;fi<startFi+count;++fi){
        auto cur=make_frame(3840,2160,fi);std::vector<EncTile>out(plan.tiles.size());
        auto t0=Clock::now();
        parallel_for(plan.tiles.size(),[&](std::size_t i,std::uint32_t){
            auto&t=plan.tiles[i];auto c=extract_tile(cur,t),p=extract_tile(prev,t);
            auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
            auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
            auto key=context_key(mapped);int a=choose_action(model,key);set_action(a);
            out[i]={t,std::move(mr.motion_map),mode,aurora_fastd_runtime_encode(mapped),(std::uint8_t)a,std::move(key)};
        });
        auto t1=Clock::now();
        parallel_for(out.size(),[&](std::size_t i,std::uint32_t){
            auto mapped=aurora_fastd_runtime_decode(out[i].packed);
            auto res=AuroraVideoResidual::unmap(mapped,out[i].mode);
            auto p=extract_tile(prev,out[i].tile);
            auto rec=AuroraVideoMotion::decode_mc8r4(out[i].motion,res,p,out[i].tile.width,out[i].tile.height);
            if(rec!=extract_tile(cur,out[i].tile))throw std::runtime_error("learned roundtrip");
        });
        std::uint64_t sz=0;for(auto&x:out){sz+=x.packed.size()+x.motion.size()+3;if(x.action==0)s.a0++;else if(x.action==1)s.a1++;else s.a2++;}
        s.ms.push_back(std::chrono::duration<double,std::milli>(t1-t0).count());s.bytes.push_back(sz);
        prev=cur;
    }
    return s;
}
static void dump_model(const std::map<std::string,ContextStats>&m){
    std::ofstream f("exp71_media_model.tsv");
    f<<"context\taction\ttrials\tavg_bytes\tavg_ms\n";
    for(auto&[k,v]:m)for(int a=0;a<3;++a)if(v.a[a].trials)
        f<<k<<"\t"<<a<<"\t"<<v.a[a].trials<<"\t"<<((double)v.a[a].total_bytes/v.a[a].trials)<<"\t"<<(v.a[a].total_ms/v.a[a].trials)<<"\n";
}
static void print_summary(const char*n,const Summary&s){
    double med=percentile(s.ms,.5),p95=percentile(s.ms,.95);
    double bs=(double)std::accumulate(s.bytes.begin(),s.bytes.end(),(std::uint64_t)0)/s.bytes.size();
    double tot=(double)(s.a0+s.a1+s.a2);
    std::cout<<"EXP71_MEDIA_PASS mode="<<n<<" median_ms="<<med<<" p95_ms="<<p95<<" fps="<<1000.0/med
             <<" mean_packed_bytes="<<bs<<" pct24="<<(100.0*s.a0/tot)<<" pct48="<<(100.0*s.a1/tot)
             <<" pct64="<<(100.0*s.a2/tot)<<" lossless=1\n";
}

int main(){
    try{
        std::map<std::string,ContextStats> model;
        train_model(model,6);
        dump_model(model);
        auto fixed=run_fixed(7,12);
        auto learned=run_learned(model,7,12);
        std::cout<<"EXP71_MEDIA_MODEL contexts="<<model.size()<<" training_frames=6\n";
        print_summary("balanced_fixed",fixed);
        print_summary("learned",learned);
        return 0;
    }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
