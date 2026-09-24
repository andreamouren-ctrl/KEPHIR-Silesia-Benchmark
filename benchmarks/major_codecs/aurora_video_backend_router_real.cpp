#include "AuroraVideoMotion.h"
#include "AuroraVideoProfiles.h"
#include "AuroraVideoResidual.h"
#include "AuroraVideoTilePlanner.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <memory>
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
    BackendPlugin(const BackendPlugin&)=delete;
    BackendPlugin& operator=(const BackendPlugin&)=delete;

    struct Instance {
        BackendPlugin* owner{};
        void* handle{};
        Instance()=default;
        explicit Instance(BackendPlugin& p):owner(&p),handle(p.create_()) {
            if(!handle) throw std::runtime_error("backend create failed");
        }
        ~Instance(){ if(handle) owner->destroy_(handle); }
        Instance(Instance&& o) noexcept:owner(o.owner),handle(o.handle){o.handle=nullptr;}
        Instance& operator=(Instance&& o) noexcept {
            if(this!=&o){ if(handle) owner->destroy_(handle); owner=o.owner;handle=o.handle;o.handle=nullptr; }
            return *this;
        }
        Instance(const Instance&)=delete;
        Instance& operator=(const Instance&)=delete;

        Bytes encode(ByteView in) {
            auto r=owner->encode_(handle,in.data(),in.size());
            if(!r.data && r.size) throw std::runtime_error("plugin encode failed");
            Bytes out(r.data,r.data+r.size);
            owner->free_(r.data);
            return out;
        }
        Bytes decode(ByteView in) {
            auto r=owner->decode_(handle,in.data(),in.size());
            if(!r.data && r.size) throw std::runtime_error("plugin decode failed");
            Bytes out(r.data,r.data+r.size);
            owner->free_(r.data);
            return out;
        }
    };

    Instance make_instance(){ return Instance(*this); }

private:
    using Create=void*(*)();
    using Destroy=void(*)(void*);
    using Codec=PluginBuffer(*)(void*,const unsigned char*,std::size_t);
    using Free=void(*)(unsigned char*);
    template<class T> T load(const char* name) {
        auto* p=dlsym(so_,name);
        if(!p) throw std::runtime_error(std::string("dlsym failed: ")+name);
        T fn{};
        static_assert(sizeof(fn)==sizeof(p));
        std::memcpy(&fn,&p,sizeof(fn));
        return fn;
    }
    void* so_{};
    Create create_{};
    Destroy destroy_{};
    Codec encode_{};
    Codec decode_{};
    Free free_{};
};

enum class BackendKind : std::uint8_t { Exp37=0,FastD=1 };

struct EncodedTile {
    VideoTile tile;
    Bytes motion;
    VideoResidualMode mode{VideoResidualMode::Mod8};
    BackendKind backend{BackendKind::Exp37};
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
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for(std::uint32_t w=0;w<workers;++w) {
        pool.emplace_back([&,w]{
            for(;;) {
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                if(i>=count) break;
                fn(i,w);
            }
        });
    }
    for(auto& t:pool) t.join();
}

static void run_case(const char* name,std::uint32_t fw,std::uint32_t fh,
                     double target_fps,
                     BackendPlugin& expPlugin,BackendPlugin& fastPlugin) {
    constexpr std::uint32_t workers=4;
    constexpr std::uint32_t frames=5;
    const double budget_ms=1000.0/target_fps;
    double threshold=2.60;

    const auto cfg=video_profile_config(VideoProfile::Balanced);
    const auto plan=make_video_tile_plan(fw,fh,cfg.tile_width,cfg.tile_height,
                                         cfg.tile_halo,cfg.max_concurrent_tiles);
    auto prev=make_frame(fw,fh,0);

    std::vector<BackendPlugin::Instance> expEnc,fastEnc,expDec,fastDec;
    for(std::uint32_t i=0;i<workers;++i) {
        expEnc.emplace_back(expPlugin.make_instance());
        fastEnc.emplace_back(fastPlugin.make_instance());
        expDec.emplace_back(expPlugin.make_instance());
        fastDec.emplace_back(fastPlugin.make_instance());
    }

    double total_encode_ms=0.0;
    std::uint64_t total_packed=0;
    std::uint64_t total_raw=0;
    std::uint64_t budget_hits=0;

    for(std::uint32_t fi=1;fi<=frames;++fi) {
        const auto cur=make_frame(fw,fh,fi);
        std::vector<EncodedTile> encoded(plan.tiles.size());

        const auto e0=Clock::now();
        parallel_for(plan.tiles.size(),workers,[&](std::size_t i,std::uint32_t worker){
            const auto& tile=plan.tiles[i];
            auto ct=extract_tile(cur,fw,fh,tile);
            auto pt=extract_tile(prev,fw,fh,tile);
            auto mr=AuroraVideoMotion::encode_mc8r4_adaptive(
                ct,pt,tile.width,tile.height,4.0,9);
            const double mean=AuroraVideoResidual::mean_signed_magnitude(mr.residual_yuv420);
            const auto mode=AuroraVideoResidual::choose_mode(mr.residual_yuv420);
            auto mapped=AuroraVideoResidual::map(mr.residual_yuv420,mode);
            const auto kind=mean<=threshold ? BackendKind::FastD : BackendKind::Exp37;
            auto packed=kind==BackendKind::FastD
                ? fastEnc[worker].encode(mapped)
                : expEnc[worker].encode(mapped);
            encoded[i]=EncodedTile{tile,std::move(mr.motion_map),mode,kind,std::move(packed)};
        });
        const auto e1=Clock::now();

        std::atomic<std::uint64_t> fastTiles{0},expTiles{0};
        std::vector<Bytes> decoded(plan.tiles.size());
        parallel_for(encoded.size(),workers,[&](std::size_t i,std::uint32_t worker){
            const auto& et=encoded[i];
            auto pt=extract_tile(prev,fw,fh,et.tile);
            auto mapped=et.backend==BackendKind::FastD
                ? fastDec[worker].decode(et.packed)
                : expDec[worker].decode(et.packed);
            if(et.backend==BackendKind::FastD) fastTiles.fetch_add(1,std::memory_order_relaxed);
            else expTiles.fetch_add(1,std::memory_order_relaxed);
            auto residual=AuroraVideoResidual::unmap(mapped,et.mode);
            decoded[i]=AuroraVideoMotion::decode_mc8r4(
                et.motion,residual,pt,et.tile.width,et.tile.height);
        });

        std::uint64_t packedBytes=0,rawBytes=0;
        for(std::size_t i=0;i<decoded.size();++i) {
            auto expected=extract_tile(cur,fw,fh,encoded[i].tile);
            if(decoded[i]!=expected)
                throw std::runtime_error(std::string("latency router roundtrip mismatch ")+name);
            packedBytes+=encoded[i].packed.size()+encoded[i].motion.size()+2;
            rawBytes+=decoded[i].size();
        }

        const double encMs=std::chrono::duration<double,std::milli>(e1-e0).count();
        const bool hit=encMs<=budget_ms;
        if(hit) ++budget_hits;

        std::cout<<"LATENCY_ROUTER_FRAME"
                 <<" name="<<name
                 <<" target_fps="<<target_fps
                 <<" frame="<<fi
                 <<" threshold="<<threshold
                 <<" fast_tiles_pct="<<(100.0*fastTiles.load()/encoded.size())
                 <<" encode_ms="<<encMs
                 <<" budget_ms="<<budget_ms
                 <<" budget_hit="<<(hit?1:0)
                 <<" packed_bytes="<<packedBytes
                 <<" ratio_percent="<<(100.0*static_cast<double>(packedBytes)/rawBytes)
                 <<" lossless=1"
                 <<"\n";

        total_encode_ms+=encMs;
        total_packed+=packedBytes;
        total_raw+=rawBytes;

        if(encMs>budget_ms) {
            threshold=std::min(5.0,threshold+0.90);
        } else if(encMs<budget_ms*0.75) {
            threshold=std::max(2.60,threshold-0.45);
        }

        prev=cur;
    }

    const double avg_ms=total_encode_ms/frames;
    std::cout<<"LATENCY_ROUTER_PASS"
             <<" name="<<name
             <<" target_fps="<<target_fps
             <<" frames="<<frames
             <<" avg_encode_ms="<<avg_ms
             <<" avg_encode_fps="<<(1000.0/avg_ms)
             <<" budget_hits="<<budget_hits
             <<" final_threshold="<<threshold
             <<" avg_ratio_percent="<<(100.0*static_cast<double>(total_packed)/total_raw)
             <<" lossless=1"
             <<"\n";
}

int main() {
    try {
        BackendPlugin exp("./libaurora_exp37.so");
        BackendPlugin fast("./libaurora_fastd.so");
        std::cout<<"hardware_concurrency="<<std::thread::hardware_concurrency()<<"\n";
        for(const double target:{30.0,60.0}) {
            run_case("1080p",1920,1080,target,exp,fast);
            run_case("1440p",2560,1440,target,exp,fast);
            run_case("4K",3840,2160,target,exp,fast);
        }
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
