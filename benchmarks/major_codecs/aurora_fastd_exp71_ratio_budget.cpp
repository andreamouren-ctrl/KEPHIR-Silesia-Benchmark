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

struct Stat{std::uint64_t n=0,b24=0,b48=0;double t24=0,t48=0;};
struct Tile{VideoTile t;Bytes motion;VideoResidualMode mode;Bytes packed;std::uint8_t a=0;};

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
template<class F>static void pf_static(std::size_t n,std::uint32_t workers,F fn){
 std::vector<std::thread>p;for(std::uint32_t k=0;k<workers;++k)p.emplace_back([&,k]{for(std::size_t i=k;i<n;i+=workers)fn(i,k);});for(auto&t:p)t.join();
}
static double entropy_sample(ByteView b){
 if(b.empty())return 0;std::array<unsigned,256>c{};std::uint64_t n=0;
 for(std::size_t i=0;i<b.size();i+=32){c[b[i]]++;n++;}
 double h=0;for(auto v:c)if(v){double p=(double)v/n;h-=p*std::log2(p);}return h;
}
static std::string key(ByteView b){
 double h=entropy_sample(b),m=AuroraVideoResidual::mean_signed_magnitude(b);std::uint64_t z=0,n=0;
 for(std::size_t i=0;i<b.size();i+=32){z+=(b[i]==0);n++;}
 double zp=n?(double)z/n:0;
 return std::to_string(std::min(7,std::max(0,(int)h)))+":"+
        std::to_string(std::min(7,std::max(0,(int)(m/1.0))))+":"+
        std::to_string(std::min(4,std::max(0,(int)(zp*10))));
}
static double pc(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}

static void train(std::map<std::string,Stat>&model){
 auto cfg=video_profile_config(VideoProfile::Streaming4K);auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);auto prev=fr(3840,2160,0);std::mutex mu;
 for(int fi=1;fi<=6;++fi){auto cur=fr(3840,2160,fi);
  pf_static(plan.tiles.size(),4,[&](std::size_t i,std::uint32_t){
   if(((i+(std::size_t)fi)%3)!=0)return;
   auto&t=plan.tiles[i];auto c=tile(cur,t),p=tile(prev,t);auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);auto k=key(mapped);
   aurora_fastd_runtime_set_depths(24,12);auto a0=Clock::now();auto e24=aurora_fastd_runtime_encode(mapped);auto a1=Clock::now();
   aurora_fastd_runtime_set_depths(48,24);auto b0=Clock::now();auto e48=aurora_fastd_runtime_encode(mapped);auto b1=Clock::now();
   if(aurora_fastd_runtime_decode(e24)!=mapped||aurora_fastd_runtime_decode(e48)!=mapped)throw std::runtime_error("train roundtrip");
   std::lock_guard<std::mutex>g(mu);auto&s=model[k];s.n++;s.b24+=e24.size();s.b48+=e48.size();s.t24+=std::chrono::duration<double,std::milli>(a1-a0).count();s.t48+=std::chrono::duration<double,std::milli>(b1-b0).count();
  });prev=cur;
 }
}
static std::vector<std::string> top_contexts(const std::map<std::string,Stat>&m,int topk){
 struct Q{std::string k;double score;double save;double cost;};
 std::vector<Q>q;
 for(auto&[k,s]:m){
  if(s.n<2)continue;
  double b24=(double)s.b24/s.n,b48=(double)s.b48/s.n,t24=s.t24/s.n,t48=s.t48/s.n;
  double save=b24-b48,cost=t48-t24;
  if(save<=0)continue;
  double score=save/std::max(0.02,cost);
  q.push_back({k,score,save,cost});
 }
 std::sort(q.begin(),q.end(),[](const Q&a,const Q&b){return a.score>b.score;});
 std::vector<std::string>out;
 for(int i=0;i<topk&&i<(int)q.size();++i)out.push_back(q[i].k);
 return out;
}
static bool use48_top(const std::vector<std::string>&top,const std::string&k){
 return std::find(top.begin(),top.end(),k)!=top.end();
}
struct R{std::vector<double>ms;std::vector<std::uint64_t>bytes;std::uint64_t c24=0,c48=0;};

static R run(const std::map<std::string,Stat>&model,int topk,bool adaptive){
 auto cfg=video_profile_config(VideoProfile::Streaming4K);auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);auto prev=fr(3840,2160,6);R r;auto top=top_contexts(model,topk);
 for(int fi=7;fi<=18;++fi){auto cur=fr(3840,2160,fi);std::vector<Tile>o(plan.tiles.size());auto t0=Clock::now();
  pf_static(plan.tiles.size(),4,[&](std::size_t i,std::uint32_t){
   auto&t=plan.tiles[i];auto c=tile(cur,t),p=tile(prev,t);auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);int a=0;
   if(adaptive && use48_top(top,key(mapped)))a=1;
   aurora_fastd_runtime_set_depths(a?48:24,a?24:12);
   o[i]=Tile{t,std::move(mr.motion_map),mode,aurora_fastd_runtime_encode(mapped),(std::uint8_t)a};
  });
  auto t1=Clock::now();
  pf_static(o.size(),4,[&](std::size_t i,std::uint32_t){
   auto mapped=aurora_fastd_runtime_decode(o[i].packed);auto res=AuroraVideoResidual::unmap(mapped,o[i].mode);auto p=tile(prev,o[i].t);auto rec=AuroraVideoMotion::decode_mc8r4(o[i].motion,res,p,o[i].t.width,o[i].t.height);if(rec!=tile(cur,o[i].t))throw std::runtime_error("roundtrip");
  });
  std::uint64_t sz=0;for(auto&x:o){sz+=x.packed.size()+x.motion.size()+3;if(x.a)r.c48++;else r.c24++;}
  r.ms.push_back(std::chrono::duration<double,std::milli>(t1-t0).count());r.bytes.push_back(sz);prev=cur;
 }return r;
}
static void pr(const char*n,const R&r){
 double med=pc(r.ms,.5),p95=pc(r.ms,.95),b=(double)std::accumulate(r.bytes.begin(),r.bytes.end(),(std::uint64_t)0)/r.bytes.size(),tot=(double)(r.c24+r.c48);
 std::cout<<"RATIO_BUDGET_PASS mode="<<n<<" median_ms="<<med<<" p95_ms="<<p95<<" fps="<<1000.0/med<<" mean_packed_bytes="<<b<<" pct24="<<100.0*r.c24/tot<<" pct48="<<100.0*r.c48/tot<<" lossless=1\n";
}
int main(){try{
 std::map<std::string,Stat>m;train(m);std::cout<<"RATIO_BUDGET_MODEL contexts="<<m.size()<<"\n";
 auto base=run(m,0,false);auto a=run(m,1,true);auto b=run(m,2,true);auto c=run(m,3,true);
 pr("fast_static",base);pr("top1",a);pr("top2",b);pr("top3",c);return 0;
}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
