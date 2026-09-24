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

struct PluginBuffer { unsigned char* data; std::size_t size; };

class BackendPlugin {
public:
    explicit BackendPlugin(const char* path) {
        so_=dlopen(path,RTLD_NOW|RTLD_LOCAL);
        if(!so_) throw std::runtime_error(std::string("dlopen failed: ")+dlerror());
        create_=load<Create>("aurora_backend_create");
        destroy_=load<Destroy>("aurora_backend_destroy");
        encode_=load<Codec>("aurora_backend_encode");
        decode_=load<Codec>("aurora_backend_decode");
        free_=load<Free>("aurora_backend_free");
    }
    ~BackendPlugin(){ if(so_) dlclose(so_); }
    struct Instance {
        BackendPlugin* owner{};
        void* handle{};
        explicit Instance(BackendPlugin& p):owner(&p),handle(p.create_()) {
            if(!handle) throw std::runtime_error("backend create failed");
        }
        ~Instance(){ if(handle) owner->destroy_(handle); }
        Instance(Instance&& o) noexcept:owner(o.owner),handle(o.handle){o.handle=nullptr;}
        Instance& operator=(Instance&& o) noexcept {
            if(this!=&o){ if(handle) owner->destroy_(handle); owner=o.owner; handle=o.handle; o.handle=nullptr; }
            return *this;
        }
        Instance(const Instance&)=delete;
        Instance& operator=(const Instance&)=delete;
        Bytes encode(ByteView in) {
            auto r=owner->encode_(handle,in.data(),in.size());
            Bytes out;
            if(r.size) {
                if(!r.data) throw std::runtime_error("plugin encode failed");
                out.assign(r.data,r.data+r.size);
            }
            owner->free_(r.data);
            return out;
        }
        Bytes decode(ByteView in) {
            auto r=owner->decode_(handle,in.data(),in.size());
            Bytes out;
            if(r.size) {
                if(!r.data) throw std::runtime_error("plugin decode failed");
                out.assign(r.data,r.data+r.size);
            }
            owner->free_(r.data);
            return out;
        }
    };
    Instance make(){ return Instance(*this); }
private:
    using Create=void*(*)();
    using Destroy=void(*)(void*);
    using Codec=PluginBuffer(*)(void*,const unsigned char*,std::size_t);
    using Free=void(*)(unsigned char*);
    template<class T> T load(const char* name) {
        auto* p=dlsym(so_,name);
        if(!p) throw std::runtime_error(std::string("dlsym failed: ")+name);
        T fn{}; static_assert(sizeof(fn)==sizeof(p)); std::memcpy(&fn,&p,sizeof(fn)); return fn;
    }
    void* so_{}; Create create_{}; Destroy destroy_{}; Codec encode_{}; Codec decode_{}; Free free_{};
};

enum class Mode { Baseline, Early, Router };
enum class Kind : std::uint8_t { Exp37=0, Fast=1 };

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode residual_mode{VideoResidualMode::Mod8};
    Kind kind{Kind::Fast};
    Bytes packed;
};

static Bytes make_frame(std::uint32_t w,std::uint32_t h,std::uint32_t fi) {
    const std::size_t ys=static_cast<std::size_t>(w)*h;
    const std::size_t us=static_cast<std::size_t>(w/2)*(h/2);
    Bytes b(ys+2*us);
    for(std::uint32_t y=0;y<h;++y)
        for(std::uint32_t x=0;x<w;++x) {
            const auto moving=((x+fi*5u)/48u+(y+fi*3u)/40u)&15u;
            b[static_cast<std::size_t>(y)*w+x]=static_cast<Byte>(
                (x*3u+y*5u+moving*7u+fi*2u)&255u);
        }
    const auto cw=w/2,ch=h/2;
    for(std::uint32_t y=0;y<ch;++y)
        for(std::uint32_t x=0;x<cw;++x) {
            const auto i=static_cast<std::size_t>(y)*cw+x;
            b[ys+i]=static_cast<Byte>((80u+x+y+fi)&255u);
            b[ys+us+i]=static_cast<Byte>((170u+2u*x+y+fi*2u)&255u);
        }
    return b;
}

static Bytes extract_tile(ByteView frame,std::uint32_t fw,std::uint32_t fh,const VideoTile& t) {
    const std::size_t ys=static_cast<std::size_t>(fw)*fh;
    const auto cw=fw/2,ch=fh/2;
    const std::size_t us=static_cast<std::size_t>(cw)*ch;
    const std::size_t tys=static_cast<std::size_t>(t.width)*t.height;
    const auto tcw=t.width/2,tch=t.height/2;
    const std::size_t tus=static_cast<std::size_t>(tcw)*tch;
    Bytes out(tys+2*tus);
    for(std::uint32_t y=0;y<t.height;++y) {
        const auto src=static_cast<std::size_t>(t.y+y)*fw+t.x;
        const auto dst=static_cast<std::size_t>(y)*t.width;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(src),t.width,
                    out.begin()+static_cast<std::ptrdiff_t>(dst));
    }
    for(std::uint32_t y=0;y<tch;++y) {
        const auto src=static_cast<std::size_t>(t.y/2+y)*cw+t.x/2;
        const auto dst=static_cast<std::size_t>(y)*tcw;
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+dst));
        std::copy_n(frame.begin()+static_cast<std::ptrdiff_t>(ys+us+src),tcw,
                    out.begin()+static_cast<std::ptrdiff_t>(tys+tus+dst));
    }
    return out;
}

template<class Fn>
static void parallel_for(std::size_t count,std::uint32_t workers,Fn fn) {
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> pool; pool.reserve(workers);
    for(std::uint32_t w=0;w<workers;++w)
        pool.emplace_back([&,w]{ for(;;){ const auto i=next.fetch_add(1,std::memory_order_relaxed); if(i>=count) break; fn(i,w); }});
    for(auto& t:pool) t.join();
}

struct Result {
    std::vector<double> ms;
    std::vector<std::uint64_t> bytes;
    std::uint64_t fast_tiles{};
    std::uint64_t exp_tiles{};
};

static Result run_mode(const char* label,Mode mode,
                       BackendPlugin& baselinePlugin,BackendPlugin& earlyPlugin,BackendPlugin& expPlugin) {
    constexpr std::uint32_t fw=3840,fh=2160,workers=4,warmup=2,measured=12;
    constexpr double threshold=2.60;
    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,cfg.tile_halo,cfg.max_concurrent_tiles);

    std::vector<BackendPlugin::Instance> baseEnc,baseDec,earlyEnc,earlyDec,expEnc,expDec;
    for(std::uint32_t i=0;i<workers;++i) {
        baseEnc.emplace_back(baselinePlugin.make()); baseDec.emplace_back(baselinePlugin.make());
        earlyEnc.emplace_back(earlyPlugin.make()); earlyDec.emplace_back(earlyPlugin.make());
        expEnc.emplace_back(expPlugin.make()); expDec.emplace_back(expPlugin.make());
    }

    Result result;
    auto prev=make_frame(fw,fh,0);
    const std::uint32_t total=warmup+measured;
    for(std::uint32_t fi=1;fi<=total;++fi) {
        const auto cur=make_frame(fw,fh,fi);
        std::vector<EncodedTile> encoded(plan.tiles.size());

        const auto e0=Clock::now();
        parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
            const auto& t=plan.tiles[i];
            auto c=extract_tile(cur,fw,fh,t);
            auto p=extract_tile(prev,fw,fh,t);
            auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(c,p,t.width,t.height,4.0,9);
            const auto rmode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            const double mean=AuroraVideoResidual::mean_signed_magnitude(mr.residual_yuv420);
            auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,rmode);

            Kind kind=Kind::Fast;
            Bytes packed;
            if(mode==Mode::Baseline) packed=baseEnc[worker].encode(mapped);
            else if(mode==Mode::Early) packed=earlyEnc[worker].encode(mapped);
            else {
                kind=(mean<=threshold)?Kind::Fast:Kind::Exp37;
                packed=(kind==Kind::Fast)?earlyEnc[worker].encode(mapped):expEnc[worker].encode(mapped);
            }
            encoded[i]=EncodedTile{t,std::move(mr.motion_map),rmode,kind,std::move(packed)};
        });
        const auto e1=Clock::now();

        std::vector<Bytes> decoded(plan.tiles.size());
        parallel_for(encoded.size(),workers,[&](std::size_t i,std::uint32_t worker){
            const auto& et=encoded[i];
            auto p=extract_tile(prev,fw,fh,et.tile);
            Bytes mapped;
            if(mode==Mode::Baseline) mapped=baseDec[worker].decode(et.packed);
            else if(mode==Mode::Early) mapped=earlyDec[worker].decode(et.packed);
            else mapped=(et.kind==Kind::Fast)?earlyDec[worker].decode(et.packed):expDec[worker].decode(et.packed);
            auto residual=AuroraVideoResidual::unmap(mapped,et.residual_mode);
            decoded[i]=AuroraVideoMotion::decode_mc8r4(et.motion,residual,p,et.tile.width,et.tile.height);
        });

        std::uint64_t packedBytes=0;
        for(std::size_t i=0;i<encoded.size();++i) {
            if(decoded[i]!=extract_tile(cur,fw,fh,encoded[i].tile))
                throw std::runtime_error(std::string("roundtrip mismatch ")+label);
            packedBytes+=encoded[i].packed.size()+encoded[i].motion.size()+2;
            if(fi>warmup && mode==Mode::Router) {
                if(encoded[i].kind==Kind::Fast) ++result.fast_tiles; else ++result.exp_tiles;
            }
        }

        if(fi>warmup) {
            const double ms=std::chrono::duration<double,std::milli>(e1-e0).count();
            result.ms.push_back(ms);
            result.bytes.push_back(packedBytes);
            std::cout<<"STABLE_AB_FRAME mode="<<label<<" frame="<<(fi-warmup)
                     <<" encode_ms="<<ms<<" packed_bytes="<<packedBytes<<" lossless=1\n";
        }
        prev=cur;
    }
    return result;
}

static double percentile(std::vector<double> v,double q) {
    std::sort(v.begin(),v.end());
    if(v.empty()) return 0.0;
    const double pos=q*static_cast<double>(v.size()-1);
    const auto lo=static_cast<std::size_t>(std::floor(pos));
    const auto hi=static_cast<std::size_t>(std::ceil(pos));
    if(lo==hi) return v[lo];
    return v[lo]+(v[hi]-v[lo])*(pos-lo);
}

static void summary(const char* label,const Result& r) {
    const double mean=std::accumulate(r.ms.begin(),r.ms.end(),0.0)/r.ms.size();
    const double median=percentile(r.ms,0.5);
    const double p95=percentile(r.ms,0.95);
    const double meanBytes=static_cast<double>(std::accumulate(r.bytes.begin(),r.bytes.end(),std::uint64_t{0}))/r.bytes.size();
    const auto tiles=r.fast_tiles+r.exp_tiles;
    std::cout<<"STABLE_AB_PASS mode="<<label
             <<" frames="<<r.ms.size()
             <<" mean_ms="<<mean
             <<" median_ms="<<median
             <<" p95_ms="<<p95
             <<" median_fps="<<(1000.0/median)
             <<" p95_fps="<<(1000.0/p95)
             <<" mean_packed_bytes="<<meanBytes;
    if(tiles) std::cout<<" fast_tiles_pct="<<(100.0*r.fast_tiles/tiles);
    std::cout<<" lossless=1\n";
}

int main() {
    try {
        std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";
        BackendPlugin baseline("./libaurora_fastd_baseline.so");
        BackendPlugin early("./libaurora_fastd_early.so");
        BackendPlugin exp("./libaurora_exp37.so");

        auto a=run_mode("baseline",Mode::Baseline,baseline,early,exp);
        auto b=run_mode("early",Mode::Early,baseline,early,exp);
        auto c=run_mode("router",Mode::Router,baseline,early,exp);
        summary("baseline",a); summary("early",b); summary("router",c);
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
