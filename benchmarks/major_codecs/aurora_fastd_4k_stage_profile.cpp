#include "AuroraKhepriFastDMemoryAdapter.h"
#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
using namespace aurora::media;
using Clock=std::chrono::steady_clock;

struct Stats{double extract{},motion{},choose{},map{},fastd{};std::uint64_t tiles{};};
struct Encoded{VideoTile tile;Bytes motion;VideoResidualMode mode{VideoResidualMode::Mod8};Bytes packed;};

static Bytes frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi){
    const std::size_t ys=static_cast<std::size_t>(w)*h,us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)for(std::uint32_t x=0;x<w;++x){
        const auto m=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;
        b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>((x*3u+y*5u+m*7u+fi*2u)&255u);
    }
    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)for(std::uint32_t x=0;x<cw;++x){
        const auto i=static_cast<std::size_t>(y)*cw+x;
        b[ys+i]=static_cast<Byte>((80u+x+y+fi)&255u);
        b[ys+us+i]=static_cast<Byte>((170u+2u*x+y+fi*2u)&255u);
    }
    return b;
}

static Bytes tile(ByteView f,std::uint32_t fw,std::uint32_t fh,const VideoTile&t){
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2,ch=fh/2; const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2,tch=t.height/2; const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    Bytes o(tys+2*tus);
    for(std::uint32_t y=0;y<t.height;++y){
        const auto s=static_cast<std::size_t>(t.y+y)*fw+t.x,d=static_cast<std::size_t>(y)*t.width;
        std::copy_n(f.begin()+static_cast<std::ptrdiff_t>(s),t.width,o.begin()+static_cast<std::ptrdiff_t>(d));
    }
    for(std::uint32_t y=0;y<tch;++y){
        const auto s=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2,d=static_cast<std::size_t>(y)*tcw;
        std::copy_n(f.begin()+static_cast<std::ptrdiff_t>(ys+s),tcw,o.begin()+static_cast<std::ptrdiff_t>(tys+d));
        std::copy_n(f.begin()+static_cast<std::ptrdiff_t>(ys+us+s),tcw,o.begin()+static_cast<std::ptrdiff_t>(tys+tus+d));
    }
    return o;
}

template<class F>static void pf(std::size_t n,std::uint32_t workers,F fn){
    std::atomic<std::size_t> next{0}; std::vector<std::thread> pool;
    for(std::uint32_t w=0;w<workers;++w)pool.emplace_back([&,w]{for(;;){auto i=next.fetch_add(1);if(i>=n)break;fn(i,w);}});
    for(auto&t:pool)t.join();
}

int main(){
 try{
    constexpr std::uint32_t w=3840,h=2160,workers=4;
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(w,h,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);
    const auto prev=frame(w,h,0),cur=frame(w,h,1);
    std::vector<Encoded> enc(plan.tiles.size());
    std::vector<AuroraKhepriFastDMemoryAdapter> k(workers);
    std::vector<Stats> st(workers);

    const auto wall0=Clock::now();
    pf(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
        const auto&t=plan.tiles[i];
        auto a=Clock::now(); auto c=tile(cur,w,h,t); auto p=tile(prev,w,h,t); auto b=Clock::now();
        auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9); auto d=Clock::now();
        auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420); auto e=Clock::now();
        auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode); auto f=Clock::now();
        auto packed=k[worker].encode(mapped); auto g=Clock::now();
        auto&s=st[worker];
        s.extract+=std::chrono::duration<double>(b-a).count();
        s.motion+=std::chrono::duration<double>(d-b).count();
        s.choose+=std::chrono::duration<double>(e-d).count();
        s.map+=std::chrono::duration<double>(f-e).count();
        s.fastd+=std::chrono::duration<double>(g-f).count(); ++s.tiles;
        enc[i]=Encoded{t,std::move(mr.motion_map),mode,std::move(packed)};
    });
    const auto wall1=Clock::now();

    for(std::size_t i=0;i<enc.size();++i){
        auto p=tile(prev,w,h,enc[i].tile);
        auto mapped=k[i%workers].decode(enc[i].packed);
        auto residual=AuroraVideoResidual::unmap(mapped,enc[i].mode);
        auto out=AuroraVideoMotion::decode_mc8r4(enc[i].motion,residual,p,enc[i].tile.width,enc[i].tile.height);
        if(out!=tile(cur,w,h,enc[i].tile))throw std::runtime_error("roundtrip mismatch");
    }

    Stats s;for(const auto&x:st){s.extract+=x.extract;s.motion+=x.motion;s.choose+=x.choose;s.map+=x.map;s.fastd+=x.fastd;s.tiles+=x.tiles;}
    const double cpu=s.extract+s.motion+s.choose+s.map+s.fastd;
    const double wall=std::chrono::duration<double,std::milli>(wall1-wall0).count();
    auto pct=[&](double x){return 100.0*x/cpu;};
    std::uint64_t bytes=0;for(const auto&e:enc)bytes+=e.packed.size()+e.motion.size()+1;
    std::cout<<"FASTD_4K_PROFILE_PASS"
      <<" hardware_concurrency="<<std::thread::hardware_concurrency()
      <<" workers="<<workers<<" tiles="<<s.tiles
      <<" wall_ms="<<wall<<" wall_fps="<<1000.0/wall
      <<" extract_cpu_ms="<<s.extract*1000<<" extract_pct="<<pct(s.extract)
      <<" motion_cpu_ms="<<s.motion*1000<<" motion_pct="<<pct(s.motion)
      <<" choose_cpu_ms="<<s.choose*1000<<" choose_pct="<<pct(s.choose)
      <<" map_cpu_ms="<<s.map*1000<<" map_pct="<<pct(s.map)
      <<" fastd_cpu_ms="<<s.fastd*1000<<" fastd_pct="<<pct(s.fastd)
      <<" cpu_sum_ms="<<cpu*1000
      <<" packed_bytes="<<bytes<<" lossless=1\n";
    return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
