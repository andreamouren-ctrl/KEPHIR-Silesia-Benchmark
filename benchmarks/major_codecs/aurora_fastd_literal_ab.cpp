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
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct PB{unsigned char*data;std::size_t size;};
class P{
public:
 using C=void*(*)();using D=void(*)(void*);using F=PB(*)(void*,const unsigned char*,std::size_t);using R=void(*)(unsigned char*);
 explicit P(const char*path){so=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!so)throw std::runtime_error(dlerror());c=L<C>("aurora_backend_create");d=L<D>("aurora_backend_destroy");e=L<F>("aurora_backend_encode");x=L<F>("aurora_backend_decode");r=L<R>("aurora_backend_free");}
 ~P(){if(so)dlclose(so);}
 struct I{P*p{};void*h{};explicit I(P&q):p(&q),h(q.c()){if(!h)throw std::runtime_error("create");}~I(){if(h)p->d(h);}I(I&&o)noexcept:p(o.p),h(o.h){o.h=nullptr;}I(const I&)=delete;Bytes call(F f,ByteView b){auto z=f(h,b.data(),b.size());Bytes o;if(z.size){if(!z.data)throw std::runtime_error("plugin");o.assign(z.data,z.data+z.size);}p->r(z.data);return o;}Bytes enc(ByteView b){return call(p->e,b);}Bytes dec(ByteView b){return call(p->x,b);}};
 I make(){return I(*this);}
private:template<class T>T L(const char*n){auto*q=dlsym(so,n);if(!q)throw std::runtime_error(n);T f{};std::memcpy(&f,&q,sizeof(f));return f;}void*so{};C c{};D d{};F e{},x{};R r{};
};
static Bytes fr(std::uint32_t w,std::uint32_t h,std::uint32_t fi){const std::size_t ys=(std::size_t)w*h,us=(std::size_t)(w/2)*(h/2);Bytes b(ys+2*us);for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;b[(std::size_t)y*w+x]=(Byte)((x*3u+y*5u+m*7u+fi*2u)&255u);}auto cw=w/2,ch=h/2;for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){auto i=(std::size_t)y*cw+x;b[ys+i]=(Byte)((80u+x+y+fi)&255u);b[ys+us+i]=(Byte)((170u+2u*x+y+fi*2u)&255u);}return b;}
static Bytes tl(ByteView f,const VideoTile&t){constexpr std::uint32_t fw=3840,fh=2160;const std::size_t ys=(std::size_t)fw*fh;auto cw=fw/2,ch=fh/2;const std::size_t us=(std::size_t)cw*ch,tys=(std::size_t)t.width*t.height;auto tcw=t.width/2,tch=t.height/2;const std::size_t tus=(std::size_t)tcw*tch;Bytes o(tys+2*tus);for(std::uint32_t y=0;y<t.height;++y){auto s=(std::size_t)(t.y+y)*fw+t.x,d=(std::size_t)y*t.width;std::copy_n(f.begin()+(std::ptrdiff_t)s,t.width,o.begin()+(std::ptrdiff_t)d);}for(std::uint32_t y=0;y<tch;++y){auto s=(std::size_t)(t.y/2+y)*cw+t.x/2,d=(std::size_t)y*tcw;std::copy_n(f.begin()+(std::ptrdiff_t)(ys+s),tcw,o.begin()+(std::ptrdiff_t)(tys+d));std::copy_n(f.begin()+(std::ptrdiff_t)(ys+us+s),tcw,o.begin()+(std::ptrdiff_t)(tys+tus+d));}return o;}
template<class F>static void pf(std::size_t n,F fn){std::atomic<std::size_t>q{0};std::vector<std::thread>p;std::exception_ptr ep;std::mutex em;for(std::uint32_t k=0;k<4;++k)p.emplace_back([&,k]{try{for(;;){auto i=q.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;fn(i,k);}}catch(...){std::lock_guard<std::mutex>g(em);if(!ep)ep=std::current_exception();}});for(auto&t:p)t.join();if(ep)std::rethrow_exception(ep);}
struct E{VideoTile t;Bytes m;VideoResidualMode mode;Bytes p;};struct V{const char*n;P&p;std::vector<P::I>e,d;std::vector<double>ms;std::vector<std::uint64_t>bytes;V(const char*a,P&b):n(a),p(b){for(int i=0;i<4;++i){e.emplace_back(p.make());d.emplace_back(p.make());}}};
static void run(V&v,const Bytes&pr,const Bytes&cu,const std::vector<VideoTile>&tiles,bool measure,int idx){std::vector<E>o(tiles.size());auto a=Clock::now();pf(tiles.size(),[&](std::size_t i,std::uint32_t w){auto&t=tiles[i];auto c=tl(cu,t),p=tl(pr,t);auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);o[i]=E{t,std::move(mr.motion_map),mode,v.e[w].enc(mapped)};});auto b=Clock::now();pf(o.size(),[&](std::size_t i,std::uint32_t w){auto mapped=v.d[w].dec(o[i].p);auto res=AuroraVideoResidual::unmap(mapped,o[i].mode);auto p=tl(pr,o[i].t);auto rec=AuroraVideoMotion::decode_mc8r4(o[i].m,res,p,o[i].t.width,o[i].t.height);if(rec!=tl(cu,o[i].t))throw std::runtime_error("roundtrip");});std::uint64_t sz=0;for(auto&x:o)sz+=x.p.size()+x.m.size()+2;if(measure){double ms=std::chrono::duration<double,std::milli>(b-a).count();v.ms.push_back(ms);v.bytes.push_back(sz);std::cout<<"LITERAL_AB_FRAME mode="<<v.n<<" frame="<<idx<<" encode_ms="<<ms<<" packed_bytes="<<sz<<" lossless=1\n";}}
static double pc(std::vector<double>v,double q){std::sort(v.begin(),v.end());double p=q*(v.size()-1);auto l=(std::size_t)std::floor(p),h=(std::size_t)std::ceil(p);return l==h?v[l]:v[l]+(v[h]-v[l])*(p-l);}
static void sm(V&v){double med=pc(v.ms,.5),p95=pc(v.ms,.95),mean=std::accumulate(v.ms.begin(),v.ms.end(),0.0)/v.ms.size(),bs=(double)std::accumulate(v.bytes.begin(),v.bytes.end(),(std::uint64_t)0)/v.bytes.size();std::cout<<"LITERAL_AB_PASS mode="<<v.n<<" mean_ms="<<mean<<" median_ms="<<med<<" p95_ms="<<p95<<" median_fps="<<1000.0/med<<" mean_packed_bytes="<<bs<<" lossless=1\n";}
int main(){try{P a("./liblit_base.so"),b("./liblit_pred.so"),c("./liblit_model.so"),d("./liblit_full.so");V va("baseline",a),vb("predictor_only",b),vc("model_only",c),vd("full_literal",d);std::vector<V*>vs{&va,&vb,&vc,&vd};auto cfg=video_profile_config(VideoProfile::Balanced);auto plan=make_video_tile_plan(3840,2160,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);auto prev=fr(3840,2160,0);for(int fi=1;fi<=14;++fi){auto cur=fr(3840,2160,fi);bool m=fi>2;int idx=m?fi-2:0;int sh=fi%4;for(int k=0;k<4;++k){auto*v=vs[(k+sh)%4];try{run(*v,prev,cur,plan.tiles,m,idx);}catch(const std::exception&e){std::cerr<<"VARIANT_FAIL mode="<<v->n<<" frame="<<idx<<" error="<<e.what()<<"\n";throw;}}prev=cur;}std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";for(auto*v:vs)sm(*v);return 0;}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
