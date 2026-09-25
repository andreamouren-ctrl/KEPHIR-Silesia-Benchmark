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

struct T {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode;
    Bytes mapped;
    Bytes packed;
};
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
template<class F>static void pf(std::size_t n,F fn){std::atomic<std::size_t>q{0};std::vector<std::thread>p;for(std::uint32_t k=0;k<4;++k)p.emplace_back([&,k]{for(;;){auto i=q.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;fn(i,k);}});for(auto&t:p)t.join();}
static double pc(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}

int main(){
 try{
  auto cfg=video_profile_config(VideoProfile::Streaming4K);
  auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
  std::vector<AuroraKhepriFastDMemoryAdapter> enc(4),dec(4);
  std::vector<double> pre,ke,post,total,ideal;
  std::vector<std::uint64_t> bytes;
  auto prev=fr(3840,2160,0);
  for(int fi=1;fi<=14;++fi){
    auto cur=fr(3840,2160,fi);std::vector<T>o(plan.tiles.size());

    auto a=Clock::now();
    pf(o.size(),[&](std::size_t i,std::uint32_t){
      auto&t=plan.tiles[i];auto c=tile(cur,t),p=tile(prev,t);
      auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
      auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
      auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
      o[i]=T{t,std::move(mr.motion_map),mode,std::move(mapped),{}};
    });
    auto b=Clock::now();

    pf(o.size(),[&](std::size_t i,std::uint32_t w){o[i].packed=enc[w].encode(o[i].mapped);});
    auto c=Clock::now();

    pf(o.size(),[&](std::size_t i,std::uint32_t w){
      auto mapped=dec[w].decode(o[i].packed);
      auto res=AuroraVideoResidual::unmap(mapped,o[i].mode);
      auto p=tile(prev,o[i].tile);
      auto rec=AuroraVideoMotion::decode_mc8r4(o[i].motion,res,p,o[i].tile.width,o[i].tile.height);
      if(rec!=tile(cur,o[i].tile))throw std::runtime_error("roundtrip");
    });
    auto d=Clock::now();

    if(fi>2){
      double pms=std::chrono::duration<double,std::milli>(b-a).count();
      double kms=std::chrono::duration<double,std::milli>(c-b).count();
      double qms=std::chrono::duration<double,std::milli>(d-c).count();
      double tms=std::chrono::duration<double,std::milli>(d-a).count();
      pre.push_back(pms);ke.push_back(kms);post.push_back(qms);total.push_back(tms);
      ideal.push_back(std::max(pms,kms));
      std::uint64_t sz=0;for(auto&x:o)sz+=x.packed.size()+x.motion.size()+2;bytes.push_back(sz);
      std::cout<<"OVERLAP_FRAME frame="<<(fi-2)<<" pre_ms="<<pms<<" fastd_ms="<<kms<<" post_ms="<<qms<<" total_ms="<<tms<<" ideal_overlap_ms="<<std::max(pms,kms)<<" packed_bytes="<<sz<<" lossless=1\n";
    }
    prev=cur;
  }
  auto meanb=(double)std::accumulate(bytes.begin(),bytes.end(),(std::uint64_t)0)/bytes.size();
  std::cout<<"OVERLAP_PASS pre_median_ms="<<pc(pre,.5)<<" fastd_median_ms="<<pc(ke,.5)<<" post_median_ms="<<pc(post,.5)<<" total_median_ms="<<pc(total,.5)<<" ideal_overlap_median_ms="<<pc(ideal,.5)<<" ideal_overlap_fps="<<1000.0/pc(ideal,.5)<<" mean_packed_bytes="<<meanb<<" lossless=1\n";
  return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
