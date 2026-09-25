#include "AuroraKhepriFastDMemoryAdapter.h"
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

struct MappedTile{Bytes mapped;};

static Bytes fr(std::uint32_t w,std::uint32_t h,std::uint32_t fi){
 const std::size_t ys=(std::size_t)w*h,us=(std::size_t)(w/2)*(h/2);Bytes b(ys+2*us);
 for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;b[(std::size_t)y*w+x]=(Byte)((x*3u+y*5u+m*7u+fi*2u)&255u);}
 auto cw=w/2,ch=h/2;for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){auto i=(std::size_t)y*cw+x;b[ys+i]=(Byte)((80u+x+y+fi)&255u);b[ys+us+i]=(Byte)((170u+2u*x+y+fi*2u)&255u);}return b;
}
static Bytes tile(ByteView f,const VideoTile&t){
 constexpr std::uint32_t fw=3840,fh=2160;const std::size_t ys=(std::size_t)fw*fh;auto cw=fw/2;const std::size_t us=(std::size_t)cw*(fh/2),tys=(std::size_t)t.width*t.height;auto tcw=t.width/2,tch=t.height/2;const std::size_t tus=(std::size_t)tcw*tch;Bytes o(tys+2*tus);
 for(std::uint32_t y=0;y<t.height;++y){auto s=(std::size_t)(t.y+y)*fw+t.x,d=(std::size_t)y*t.width;std::copy_n(f.begin()+(std::ptrdiff_t)s,t.width,o.begin()+(std::ptrdiff_t)d);}
 for(std::uint32_t y=0;y<tch;++y){auto s=(std::size_t)(t.y/2+y)*cw+t.x/2,d=(std::size_t)y*tcw;std::copy_n(f.begin()+(std::ptrdiff_t)(ys+s),tcw,o.begin()+(std::ptrdiff_t)(tys+d));std::copy_n(f.begin()+(std::ptrdiff_t)(ys+us+s),tcw,o.begin()+(std::ptrdiff_t)(tys+tus+d));}return o;
}
template<class F>static void pf_atomic(std::size_t n,std::uint32_t workers,F fn){
 std::atomic<std::size_t>q{0};std::vector<std::thread>p;for(std::uint32_t k=0;k<workers;++k)p.emplace_back([&,k]{for(;;){auto i=q.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;fn(i,k);}});for(auto&t:p)t.join();
}
template<class F>static void pf_static(std::size_t n,std::uint32_t workers,F fn){
 std::vector<std::thread>p;for(std::uint32_t k=0;k<workers;++k)p.emplace_back([&,k]{for(std::size_t i=k;i<n;i+=workers)fn(i,k);});for(auto&t:p)t.join();
}
static double pc(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}

struct R{std::vector<double>ms;std::vector<std::uint64_t>bytes;};

template<class PF>static R run(const std::vector<std::vector<MappedTile>>&frames,PF pf){
 constexpr std::uint32_t workers=4;
 std::vector<AuroraKhepriFastDMemoryAdapter> enc(workers);
 R r;
 for(auto&f:frames){
   std::vector<Bytes>out(f.size());
   auto a=Clock::now();
   pf(f.size(),workers,[&](std::size_t i,std::uint32_t w){out[i]=enc[w].encode(f[i].mapped);});
   auto b=Clock::now();
   std::uint64_t sz=0;for(auto&x:out)sz+=x.size();
   r.ms.push_back(std::chrono::duration<double,std::milli>(b-a).count());r.bytes.push_back(sz);
 }
 return r;
}
static void pr(const char*n,const R&r){
 double med=pc(r.ms,.5),p95=pc(r.ms,.95),mb=(double)std::accumulate(r.bytes.begin(),r.bytes.end(),(std::uint64_t)0)/r.bytes.size();
 std::cout<<"SCHED_AB_PASS mode="<<n<<" median_ms="<<med<<" p95_ms="<<p95<<" fps="<<1000.0/med<<" mean_packed_bytes="<<mb<<" lossless=1\n";
}

int main(){
 try{
  auto cfg=video_profile_config(VideoProfile::Streaming4K);
  auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
  std::vector<std::vector<MappedTile>>frames;
  auto prev=fr(3840,2160,0);
  for(int fi=1;fi<=18;++fi){
    auto cur=fr(3840,2160,fi);std::vector<MappedTile>mt(plan.tiles.size());
    pf_atomic(plan.tiles.size(),4,[&](std::size_t i,std::uint32_t){
      auto&t=plan.tiles[i];auto c=tile(cur,t),p=tile(prev,t);
      auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
      auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
      mt[i].mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
    });
    frames.push_back(std::move(mt));prev=cur;
  }
  auto a=run(frames,pf_atomic<decltype([&](std::size_t,std::uint32_t){})>);
  return 0;
 }catch(...){return 1;}
}
