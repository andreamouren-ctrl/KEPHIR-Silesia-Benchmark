#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <thread>
#include <vector>
using namespace aurora::media;
using Clock=std::chrono::steady_clock;

extern "C" void aurora_fastd_runtime_set_depths(int,int);
extern "C" Bytes aurora_fastd_runtime_encode(ByteView);
extern "C" Bytes aurora_fastd_runtime_decode(ByteView);

struct ET{VideoTile t;Bytes m;VideoResidualMode mode;Bytes p;std::uint8_t depth_id;};
static Bytes frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi){const std::size_t ys=(std::size_t)w*h,us=(std::size_t)(w/2)*(h/2);Bytes b(ys+2*us);for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;b[(std::size_t)y*w+x]=(Byte)((x*3u+y*5u+m*7u+fi*2u)&255u);}auto cw=w/2,ch=h/2;for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){auto i=(std::size_t)y*cw+x;b[ys+i]=(Byte)((80u+x+y+fi)&255u);b[ys+us+i]=(Byte)((170u+2u*x+y+fi*2u)&255u);}return b;}
static Bytes tile(ByteView f,const VideoTile&t){constexpr std::uint32_t fw=3840,fh=2160;const std::size_t ys=(std::size_t)fw*fh;auto cw=fw/2;const std::size_t us=(std::size_t)cw*(fh/2),tys=(std::size_t)t.width*t.height;auto tcw=t.width/2,tch=t.height/2;const std::size_t tus=(std::size_t)tcw*tch;Bytes o(tys+2*tus);for(std::uint32_t y=0;y<t.height;++y){auto s=(std::size_t)(t.y+y)*fw+t.x,d=(std::size_t)y*t.width;std::copy_n(f.begin()+(std::ptrdiff_t)s,t.width,o.begin()+(std::ptrdiff_t)d);}for(std::uint32_t y=0;y<tch;++y){auto s=(std::size_t)(t.y/2+y)*cw+t.x/2,d=(std::size_t)y*tcw;std::copy_n(f.begin()+(std::ptrdiff_t)(ys+s),tcw,o.begin()+(std::ptrdiff_t)(tys+d));std::copy_n(f.begin()+(std::ptrdiff_t)(ys+us+s),tcw,o.begin()+(std::ptrdiff_t)(tys+tus+d));}return o;}
template<class F>static void pf(std::size_t n,F fn){std::atomic<std::size_t>q{0};std::vector<std::thread>p;for(std::uint32_t k=0;k<4;++k)p.emplace_back([&,k]{for(;;){auto i=q.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;fn(i,k);}});for(auto&t:p)t.join();}
static double pc(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}

struct Result{std::vector<double>ms;std::vector<std::uint64_t>bytes;std::uint64_t c24=0,c48=0,c64=0;};

static void choose_depth(ByteView mapped,int mode,double t1,double t2,std::uint8_t&id){
    if(mode==0){aurora_fastd_runtime_set_depths(48,24);id=1;return;}
    double m=AuroraVideoResidual::mean_signed_magnitude(mapped);
    if(m<=t1){aurora_fastd_runtime_set_depths(24,12);id=0;}
    else if(m<=t2){aurora_fastd_runtime_set_depths(48,24);id=1;}
    else{aurora_fastd_runtime_set_depths(64,32);id=2;}
}

static Result run_mode(int router,double t1,double t2){
    auto cfg=video_profile_config(VideoProfile::Balanced);auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    auto prev=frame(3840,2160,0);Result r;
    for(int fi=1;fi<=14;++fi){auto cur=frame(3840,2160,fi);std::vector<ET>o(plan.tiles.size());auto a=Clock::now();
      pf(plan.tiles.size(),[&](std::size_t i,std::uint32_t){auto&t=plan.tiles[i];auto c=tile(cur,t),p=tile(prev,t);auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);std::uint8_t id=1;if(router)choose_depth(mapped,1,t1,t2,id);else aurora_fastd_runtime_set_depths(48,24);o[i]=ET{t,std::move(mr.motion_map),mode,aurora_fastd_runtime_encode(mapped),id};});
      auto b=Clock::now();
      pf(o.size(),[&](std::size_t i,std::uint32_t){auto mapped=aurora_fastd_runtime_decode(o[i].p);auto res=AuroraVideoResidual::unmap(mapped,o[i].mode);auto p=tile(prev,o[i].t);auto rec=AuroraVideoMotion::decode_mc8r4(o[i].m,res,p,o[i].t.width,o[i].t.height);if(rec!=tile(cur,o[i].t))throw std::runtime_error("roundtrip");});
      if(fi>2){std::uint64_t sz=0;for(auto&x:o){sz+=x.p.size()+x.m.size()+3;if(x.depth_id==0)r.c24++;else if(x.depth_id==1)r.c48++;else r.c64++;}r.ms.push_back(std::chrono::duration<double,std::milli>(b-a).count());r.bytes.push_back(sz);}prev=cur;
    }return r;
}
static void print(const char*n,const Result&r){double med=pc(r.ms,.5),p95=pc(r.ms,.95),bs=(double)std::accumulate(r.bytes.begin(),r.bytes.end(),(std::uint64_t)0)/r.bytes.size(),tot=(double)(r.c24+r.c48+r.c64);std::cout<<"REALTIME_ROUTER_PASS mode="<<n<<" median_ms="<<med<<" p95_ms="<<p95<<" fps="<<1000.0/med<<" mean_packed_bytes="<<bs<<" pct24="<<100.0*r.c24/tot<<" pct48="<<100.0*r.c48/tot<<" pct64="<<100.0*r.c64/tot<<" lossless=1\n";}
int main(){try{auto base=run_mode(0,0,0);auto a=run_mode(1,1.8,3.6);auto b=run_mode(1,2.6,5.0);auto c=run_mode(1,3.4,6.5);print("balanced_fixed",base);print("router_1",a);print("router_2",b);print("router_3",c);return 0;}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
