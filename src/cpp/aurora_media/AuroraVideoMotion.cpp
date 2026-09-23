#include "AuroraVideoMotion.h"
#include "AuroraMediaError.h"
#include <algorithm>
#include <cstdlib>
#include <limits>
#include <tuple>

namespace aurora::media {
namespace {

std::size_t y_size(std::uint32_t w,std::uint32_t h) {
    return static_cast<std::size_t>(w)*h;
}
std::size_t uv_size(std::uint32_t w,std::uint32_t h) {
    return static_cast<std::size_t>(w/2)*(h/2);
}
std::size_t frame_size(std::uint32_t w,std::uint32_t h) {
    return y_size(w,h)+2*uv_size(w,h);
}

} // namespace

std::vector<std::pair<int,int>> AuroraVideoMotion::candidates(int radius) {
    if(radius <= 0 || (radius % 2)!=0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"motion radius must be positive and even");
    std::vector<std::pair<int,int>> c;
    for(int dy=-radius;dy<=radius;dy+=2)
        for(int dx=-radius;dx<=radius;dx+=2)
            c.emplace_back(dx,dy);

    std::sort(c.begin(),c.end(),[](const auto& a,const auto& b){
        return std::tuple{
            std::abs(a.first)+std::abs(a.second),
            std::abs(a.second),
            std::abs(a.first),
            a.second,
            a.first
        } < std::tuple{
            std::abs(b.first)+std::abs(b.second),
            std::abs(b.second),
            std::abs(b.first),
            b.second,
            b.first
        };
    });
    return c;
}

MotionResidual AuroraVideoMotion::encode_mc8r4(ByteView cur,ByteView prev,
                                               std::uint32_t w,std::uint32_t h) {
    return encode_mc8r4_limited(cur,prev,w,h,25);
}

MotionResidual AuroraVideoMotion::encode_mc8r4_limited(ByteView cur,ByteView prev,
                                                       std::uint32_t w,std::uint32_t h,
                                                       std::size_t max_candidates) {
    constexpr std::uint32_t block=8;
    constexpr int radius=4;
    if(w==0 || h==0 || (w%block)!=0 || (h%block)!=0 || (w%2)!=0 || (h%2)!=0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 invalid dimensions");
    const auto fs=frame_size(w,h);
    if(cur.size()!=fs || prev.size()!=fs)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 frame size mismatch");

    auto cand=candidates(radius);
    if(max_candidates==0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 candidate limit must be positive");
    if(max_candidates<cand.size()) cand.resize(max_candidates);
    const auto ys=y_size(w,h);
    const auto us=uv_size(w,h);
    const auto cw=w/2;

    MotionResidual out;
    out.motion_map.reserve(static_cast<std::size_t>(w/block)*(h/block));
    out.residual_yuv420.resize(fs);

    auto residual_plane=[&](std::size_t cur_off,std::size_t prev_off,std::size_t out_off,
                            std::uint32_t stride,std::uint32_t x,std::uint32_t y,
                            std::uint32_t bs,int dx,int dy) {
        for(std::uint32_t yy=0;yy<bs;++yy)
            for(std::uint32_t xx=0;xx<bs;++xx) {
                const auto ci=cur_off+static_cast<std::size_t>(y+yy)*stride+(x+xx);
                const auto pi=prev_off+static_cast<std::size_t>(static_cast<int>(y)+dy+static_cast<int>(yy))*stride+
                              static_cast<std::size_t>(static_cast<int>(x)+dx+static_cast<int>(xx));
                const int d=static_cast<int>(cur[ci])-static_cast<int>(prev[pi]);
                out.residual_yuv420[out_off+static_cast<std::size_t>(y+yy)*stride+(x+xx)]
                    = static_cast<Byte>(d & 0xff);
            }
    };

    for(std::uint32_t by=0;by<h;by+=block) {
        for(std::uint32_t bx=0;bx<w;bx+=block) {
            int best_idx=-1;
            std::uint64_t best_cost=std::numeric_limits<std::uint64_t>::max();

            for(std::size_t i=0;i<cand.size();++i) {
                const auto [dx,dy]=cand[i];
                const int sx=static_cast<int>(bx)+dx;
                const int sy=static_cast<int>(by)+dy;
                if(sx<0 || sy<0 || sx+static_cast<int>(block)>static_cast<int>(w) ||
                   sy+static_cast<int>(block)>static_cast<int>(h)) continue;

                std::uint64_t cost=0;
                for(std::uint32_t yy=0;yy<block;++yy)
                    for(std::uint32_t xx=0;xx<block;++xx) {
                        const auto ci=static_cast<std::size_t>(by+yy)*w+(bx+xx);
                        const auto pi=static_cast<std::size_t>(sy+static_cast<int>(yy))*w+
                                      static_cast<std::size_t>(sx+static_cast<int>(xx));
                        cost += static_cast<std::uint64_t>(
                            std::abs(static_cast<int>(cur[ci])-static_cast<int>(prev[pi])));
                    }
                if(cost<best_cost) {
                    best_cost=cost;
                    best_idx=static_cast<int>(i);
                }
            }

            if(best_idx<0)
                throw AuroraMediaError(ErrorCode::InternalInvariant,"MC8R4 found no candidate");

            out.motion_map.push_back(static_cast<Byte>(best_idx));
            const auto [dx,dy]=cand[static_cast<std::size_t>(best_idx)];

            residual_plane(0,0,0,w,bx,by,block,dx,dy);

            const auto cb=block/2;
            const auto cx=bx/2;
            const auto cy=by/2;
            const auto cdx=dx/2;
            const auto cdy=dy/2;
            residual_plane(ys,ys,ys,cw,cx,cy,cb,cdx,cdy);
            residual_plane(ys+us,ys+us,ys+us,cw,cx,cy,cb,cdx,cdy);
        }
    }
    return out;
}

Bytes AuroraVideoMotion::decode_mc8r4(ByteView motion,ByteView residual,ByteView prev,
                                      std::uint32_t w,std::uint32_t h) {
    constexpr std::uint32_t block=8;
    constexpr int radius=4;
    const auto fs=frame_size(w,h);
    const auto blocks=static_cast<std::size_t>(w/block)*(h/block);
    if(prev.size()!=fs || residual.size()!=fs || motion.size()!=blocks)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 decode size mismatch");

    const auto cand=candidates(radius);
    const auto ys=y_size(w,h);
    const auto us=uv_size(w,h);
    const auto cw=w/2;
    Bytes out(fs);

    auto reconstruct=[&](std::size_t prev_off,std::size_t res_off,std::size_t out_off,
                         std::uint32_t stride,std::uint32_t x,std::uint32_t y,
                         std::uint32_t bs,int dx,int dy) {
        for(std::uint32_t yy=0;yy<bs;++yy)
            for(std::uint32_t xx=0;xx<bs;++xx) {
                const auto oi=out_off+static_cast<std::size_t>(y+yy)*stride+(x+xx);
                const auto pi=prev_off+static_cast<std::size_t>(static_cast<int>(y)+dy+static_cast<int>(yy))*stride+
                              static_cast<std::size_t>(static_cast<int>(x)+dx+static_cast<int>(xx));
                const auto ri=res_off+static_cast<std::size_t>(y+yy)*stride+(x+xx);
                out[oi]=static_cast<Byte>((static_cast<unsigned>(prev[pi])+residual[ri])&0xffu);
            }
    };

    std::size_t mi=0;
    for(std::uint32_t by=0;by<h;by+=block) {
        for(std::uint32_t bx=0;bx<w;bx+=block) {
            const auto idx=motion[mi++];
            if(idx>=cand.size())
                throw AuroraMediaError(ErrorCode::CorruptPacket,"MC8R4 bad motion index");
            const auto [dx,dy]=cand[idx];
            const int sx=static_cast<int>(bx)+dx;
            const int sy=static_cast<int>(by)+dy;
            if(sx<0 || sy<0 || sx+static_cast<int>(block)>static_cast<int>(w) ||
               sy+static_cast<int>(block)>static_cast<int>(h))
                throw AuroraMediaError(ErrorCode::CorruptPacket,"MC8R4 vector out of bounds");

            reconstruct(0,0,0,w,bx,by,block,dx,dy);
            const auto cb=block/2;
            const auto cx=bx/2;
            const auto cy=by/2;
            const auto cdx=dx/2;
            const auto cdy=dy/2;
            reconstruct(ys,ys,ys,cw,cx,cy,cb,cdx,cdy);
            reconstruct(ys+us,ys+us,ys+us,cw,cx,cy,cb,cdx,cdy);
        }
    }
    return out;
}

} // namespace aurora::media
