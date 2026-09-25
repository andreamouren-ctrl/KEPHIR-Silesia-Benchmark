#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct PluginBuffer{unsigned char* data;std::size_t size;};
class Plugin{
public:
 explicit Plugin(const char* p){so=dlopen(p,RTLD_NOW|RTLD_LOCAL);if(!so)throw std::runtime_error(dlerror());create=load<C>("aurora_backend_create");destroy=load<D>("aurora_backend_destroy");enc=load<F>("aurora_backend_encode");dec=load<F>("aurora_backend_decode");fre=load<R>("aurora_backend_free");}
 ~Plugin(){if(so)dlclose(so);}
 struct I{
   Plugin* p{};void* h{};
   explicit I(Plugin&x):p(&x),h(x.create()){if(!h)throw std::runtime_error("create fail");}
   ~I(){if(h)p->destroy(h);}
   I(I&&o)noexcept:p(o.p),h(o.h){o.h=nullptr;} I(const I&)=delete;
   Bytes run(F f,ByteView in){auto r=f(h,in.data(),in.size());Bytes o;if(r.size){if(!r.data)throw std::runtime_error("plugin fail");o.assign(r.data,r.data+r.size);}p->fre(r.data);return o;}
   Bytes encode(ByteView b){return run(p->enc,b);} Bytes decode(ByteView b){return run(p->dec,b);}
 };
 I make(){return I(*this);}
private:
 using C=void*(*)();using D=void(*)(void*);using F=PluginBuffer(*)(void*,const unsigned char*,std::size_t);using R=void(*)(unsigned char*);
 template<class T>T load(const char*n){auto*q=dlsym(so,n);if(!q)throw std::runtime_error(n);T f{};std::memcpy(&f,&q,sizeof(f));return f;}
 void*so{};C create{};D destroy{};F enc{},dec{};R fre{};
};

static Bytes frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi){
 const std::size_t ys=(std::size_t)w*h,us=(std::size_t)(w/2)*(h/2);Bytes b(ys+2*us);
 for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;b[(std::size_t)y*w+x]=(Byte)((x*3u+y*5u+m*7u+fi*2u)&255u);}
 auto cw=w/2,ch=h/2;for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){auto i=(std::size_t)y*cw+x;b[ys+i]=(Byte)((80u+x+y+fi)&255u);b[ys+us+i]=(Byte)((170u+2u*x+y+fi*2u)&255u);}return b;
}
static Bytes tile(ByteView f,std::uint32_t fw,std::uint32_t fh,const VideoTile&t){
 const std::size_t ys=(std::size_t)fw*fh;auto cw=fw/2,ch=fh/2;const std::size_t us=(std::size_t)cw*ch,tys=(std::size_t)t.width*t.height;auto tcw=t.width/2,tch=t.height/2;const std::size_t tus=(std::size_t)tcw*tch;Bytes o(tys+2*tus);
 for(std::uint32_t y=0;y<t.height;++y){auto s=(std::size_t)(t.y+y)*fw+t.x,d=(std::size_t)y*t.width;std::copy_n(f.begin()+(std::ptrdiff_t)s,t.width,o.begin()+(std::ptrdiff_t)d);}
 for(std::uint32_t y=0;y<tch;++y){auto s=(std::size_t)(t.y/2+y)*cw+t.x/2,d=(std::size_t)y*tcw;std::copy_n(f.begin()+(std::ptrdiff_t)(ys+s),tcw,o.begin()+(std::ptrdiff_t)(tys+d));std::copy_n(f.begin()+(std::ptrdiff_t)(ys+us+s),tcw,o.begin()+(std::ptrdiff_t)(tys+tus+d));}return o;
}
template<class F>static void pf(std::size_t n,std::uint32_t w,F fn){std::atomic<std::size_t>next{0};std::vector<std::thread>p;for(std::uint32_t k=0;k<w;++k)p.emplace_back([&,k]{for(;;){auto i=next.fetch_add(1);if(i>=n)break;fn(i,k);}});for(auto&t:p)t.join();}
struct E{VideoTile t;Bytes m;VideoResidualMode mode;Bytes p;};
struct V{const char*name;Plugin&plug;std::vector<Plugin::I>e,d;std::vector<double>ms;std::vector<std::uint64_t>bytes;V(const char*n,Plugin&p):name(n),plug(p){for(int i=0;i<4;++i){e.emplace_back(plug.make());d.emplace_back(plug.make());}}};

static void run(V&v,const Bytes&prev,const Bytes&cur,const std::vector<VideoTile>&tiles,bool measure,int idx){
 std::vector<E> out(tiles.size());auto a=Clock::now();
 pf(tiles.size(),4,[&](std::size_t i,std::uint32_t w){auto&t=tiles[i];auto c=tile(cur,3840,2160,t),p=tile(prev,3840,2160,t);auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);auto pack=v.e[w].encode(mapped);out[i]=E{t,std::move(mr.motion_map),mode,std::move(pack)};});
 auto b=Clock::now();std::uint64_t sz=0;
 pf(out.size(),4,[&](std::size_t i,std::uint32_t w){auto mapped=v.d[w].decode(out[i].p);auto res=AuroraVideoResidual::unmap(mapped,out[i].mode);auto p=tile(prev,3840,2160,out[i].t);auto rec=AuroraVideoMotion::decode_mc8r4(out[i].m,res,p,out[i].t.width,out[i].t.height);if(rec!=tile(cur,3840,2160,out[i].t))throw std::runtime_error("roundtrip");});
 for(auto&x:out)sz+=x.p.size()+x.m.size()+2;
 if(measure){double ms=std::chrono::duration<double,std::milli>(b-a).count();v.ms.push_back(ms);v.bytes.push_back(sz);std::cout<<"EXP65_VIDEO_FRAME mode="<<v.name<<" frame="<<idx<<" encode_ms="<<ms<<" packed_bytes="<<sz<<" lossless=1\n";}
}
static double pct(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}
static void sum(V&v){double mean=std::accumulate(v.ms.begin(),v.ms.end(),0.0)/v.ms.size(),med=pct(v.ms,.5),p95=pct(v.ms,.95),bs=(double)std::accumulate(v.bytes.begin(),v.bytes.end(),(std::uint64_t)0)/v.bytes.size();std::cout<<"EXP65_VIDEO_PASS mode="<<v.name<<" mean_ms="<<mean<<" median_ms="<<med<<" p95_ms="<<p95<<" median_fps="<<1000.0/med<<" mean_packed_bytes="<<bs<<" lossless=1\n";}
int main(){try{Plugin pfst("./libfastd.so"),p37("./libexp37.so"),p65("./libexp65media.so");V fast("fastd",pfst),e37("exp37",p37),e65("exp65media",p65);auto cfg=video_profile_config(VideoProfile::Balanced);auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);auto prev=frame(3840,2160,0);for(int fi=1;fi<=14;++fi){auto cur=frame(3840,2160,fi);bool m=fi>2;int idx=m?fi-2:0;if(fi%3==1){run(fast,prev,cur,plan.tiles,m,idx);run(e37,prev,cur,plan.tiles,m,idx);run(e65,prev,cur,plan.tiles,m,idx);}else if(fi%3==2){run(e65,prev,cur,plan.tiles,m,idx);run(fast,prev,cur,plan.tiles,m,idx);run(e37,prev,cur,plan.tiles,m,idx);}else{run(e37,prev,cur,plan.tiles,m,idx);run(e65,prev,cur,plan.tiles,m,idx);run(fast,prev,cur,plan.tiles,m,idx);}prev=cur;}std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";sum(fast);sum(e37);sum(e65);return 0;}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
