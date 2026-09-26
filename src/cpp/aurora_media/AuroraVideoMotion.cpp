#include "AuroraVideoMotion.h"
#include "AuroraMediaError.h"
#include <algorithm>
#include <cstdlib>
#include <limits>
#include <tuple>
#if defined(__SSE2__)
#include <emmintrin.h>
#endif

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

std::uint64_t sad8x8(ByteView cur,ByteView prev,
                    std::uint32_t stride,
                    std::uint32_t cx,std::uint32_t cy,
                    std::uint32_t px,std::uint32_t py,
                    std::uint64_t stop_at) {
#if defined(AURORA_DISABLE_HALF_SAD_BOUND)
    (void)stop_at;
#endif
#if defined(__SSE2__)
    std::uint64_t sum=0;
    for(std::uint32_t yy=0;yy<4;++yy) {
        const auto* ca=cur.data()+static_cast<std::size_t>(cy+yy)*stride+cx;
        const auto* pa=prev.data()+static_cast<std::size_t>(py+yy)*stride+px;
        const __m128i a=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(ca));
        const __m128i b=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(pa));
        const __m128i s=_mm_sad_epu8(a,b);
        sum += static_cast<std::uint64_t>(_mm_cvtsi128_si64(s));
    }
#if !defined(AURORA_DISABLE_HALF_SAD_BOUND)
    // The partial SAD is monotonic. If half the block already reaches the
    // current best cost, the candidate cannot become strictly better.
    if(sum>=stop_at)
        return sum;
#endif
    for(std::uint32_t yy=4;yy<8;++yy) {
        const auto* ca=cur.data()+static_cast<std::size_t>(cy+yy)*stride+cx;
        const auto* pa=prev.data()+static_cast<std::size_t>(py+yy)*stride+px;
        const __m128i a=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(ca));
        const __m128i b=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(pa));
        const __m128i s=_mm_sad_epu8(a,b);
        sum += static_cast<std::uint64_t>(_mm_cvtsi128_si64(s));
    }
    return sum;
#else
    std::uint64_t sum=0;
    for(std::uint32_t yy=0;yy<4;++yy)
        for(std::uint32_t xx=0;xx<8;++xx) {
            const auto ci=static_cast<std::size_t>(cy+yy)*stride+(cx+xx);
            const auto pi=static_cast<std::size_t>(py+yy)*stride+(px+xx);
            sum += static_cast<std::uint64_t>(
                std::abs(static_cast<int>(cur[ci])-static_cast<int>(prev[pi])));
        }
#if !defined(AURORA_DISABLE_HALF_SAD_BOUND)
    if(sum>=stop_at)
        return sum;
#endif
    for(std::uint32_t yy=4;yy<8;++yy)
        for(std::uint32_t xx=0;xx<8;++xx) {
            const auto ci=static_cast<std::size_t>(cy+yy)*stride+(cx+xx);
            const auto pi=static_cast<std::size_t>(py+yy)*stride+(px+xx);
            sum += static_cast<std::uint64_t>(
                std::abs(static_cast<int>(cur[ci])-static_cast<int>(prev[pi])));
        }
    return sum;
#endif
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

double AuroraVideoMotion::sparse_luma_mad(ByteView cur,ByteView prev,
                                        std::uint32_t w,std::uint32_t h,
                                        std::uint32_t sample_step) {
    if(w==0 || h==0 || sample_step==0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"sparse MAD invalid geometry");
    const auto fs=frame_size(w,h);
    if(cur.size()!=fs || prev.size()!=fs)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"sparse MAD frame size mismatch");

    std::uint64_t sum=0;
    std::uint64_t count=0;
    for(std::uint32_t y=0;y<h;y+=sample_step) {
        const auto row=static_cast<std::size_t>(y)*w;
        for(std::uint32_t x=0;x<w;x+=sample_step) {
            sum += static_cast<std::uint64_t>(
                std::abs(static_cast<int>(cur[row+x])-static_cast<int>(prev[row+x])));
            ++count;
        }
    }
    return count ? static_cast<double>(sum)/static_cast<double>(count) : 0.0;
}

MotionResidual AuroraVideoMotion::encode_mc8r4_adaptive(ByteView cur,ByteView prev,
                                                        std::uint32_t w,std::uint32_t h,
                                                        double low_motion_threshold,
                                                        std::size_t low_motion_candidates) {
    if(low_motion_threshold<0.0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"adaptive threshold must be non-negative");
    if(low_motion_candidates==0 || low_motion_candidates>25)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"adaptive candidate count must be 1..25");

    const auto activity=sparse_luma_mad(cur,prev,w,h,8);
    const auto limit=activity<=low_motion_threshold ? low_motion_candidates : 25u;
    return encode_mc8r4_limited(cur,prev,w,h,limit);
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

    static const auto cand=candidates(radius);
    if(max_candidates==0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 candidate limit must be positive");
    const auto candidate_count=std::min<std::size_t>(max_candidates,cand.size());
    const auto ys=y_size(w,h);
    const auto us=uv_size(w,h);
    const auto cw=w/2;

    MotionResidual out;
    out.motion_map.reserve(static_cast<std::size_t>(w/block)*(h/block));
    out.residual_yuv420.resize(fs);

    auto residual_plane=[&](std::size_t cur_off,std::size_t prev_off,std::size_t out_off,
                            std::uint32_t stride,std::uint32_t x,std::uint32_t y,
                            std::uint32_t bs,int dx,int dy) {
        for(std::uint32_t yy=0;yy<bs;++yy) {
            const auto ci=cur_off+static_cast<std::size_t>(y+yy)*stride+x;
            const auto pi=prev_off+
                static_cast<std::size_t>(static_cast<int>(y)+dy+static_cast<int>(yy))*stride+
                static_cast<std::size_t>(static_cast<int>(x)+dx);
            const auto oi=out_off+static_cast<std::size_t>(y+yy)*stride+x;
#if defined(__SSE2__) && !defined(AURORA_DISABLE_RESIDUAL_SIMD)
            if(bs==8) {
                const __m128i a=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(cur.data()+ci));
                const __m128i b=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(prev.data()+pi));
                const __m128i d=_mm_sub_epi8(a,b);
                _mm_storel_epi64(
                    reinterpret_cast<__m128i*>(out.residual_yuv420.data()+oi),d);
                continue;
            }
#endif
            for(std::uint32_t xx=0;xx<bs;++xx) {
                const int d=static_cast<int>(cur[ci+xx])-static_cast<int>(prev[pi+xx]);
                out.residual_yuv420[oi+xx]=static_cast<Byte>(d & 0xff);
            }
        }
    };

    for(std::uint32_t by=0;by<h;by+=block) {
        for(std::uint32_t bx=0;bx<w;bx+=block) {
            int best_idx=-1;
            std::uint64_t best_cost=std::numeric_limits<std::uint64_t>::max();

#if defined(AURORA_DISABLE_INTERIOR_MOTION_FASTPATH)
            constexpr bool interior=false;
#else
            // For blocks at least radius pixels from every tile edge, every
            // ordered MC8R4 candidate is guaranteed in bounds. The candidate
            // set and order remain unchanged; only redundant boundary checks
            // are removed from the hot loop.
            const bool interior=
                bx>=static_cast<std::uint32_t>(radius) &&
                by>=static_cast<std::uint32_t>(radius) &&
                bx+block+static_cast<std::uint32_t>(radius)<=w &&
                by+block+static_cast<std::uint32_t>(radius)<=h;
#endif

            for(std::size_t i=0;i<candidate_count;++i) {
                const auto [dx,dy]=cand[i];
                const int sx=static_cast<int>(bx)+dx;
                const int sy=static_cast<int>(by)+dy;
                if(!interior &&
                   (sx<0 || sy<0 ||
                    sx+static_cast<int>(block)>static_cast<int>(w) ||
                    sy+static_cast<int>(block)>static_cast<int>(h)))
                    continue;

                const std::uint64_t cost=sad8x8(
                    cur,prev,w,bx,by,
                    static_cast<std::uint32_t>(sx),
                    static_cast<std::uint32_t>(sy),
                    best_cost);
                if(cost<best_cost) {
                    best_cost=cost;
                    best_idx=static_cast<int>(i);

                    // Exact fast path: SAD is non-negative, so zero is the
                    // global optimum. Candidate order is the tie-break rule
                    // (the encoder only accepts strictly lower costs), hence
                    // stopping here is bitstream-identical to evaluating all
                    // remaining candidates.
#if !defined(AURORA_DISABLE_EXACT_MOTION_FASTPATH)
                    if(best_cost==0)
                        break;
#endif
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


MotionResidual AuroraVideoMotion::encode_mc8r4_shortlist(ByteView cur,ByteView prev,
                                                         std::uint32_t w,std::uint32_t h,
                                                         std::uint32_t shortlist) {
    constexpr std::uint32_t block=8;
    constexpr int radius=4;
    if(shortlist==0 || shortlist>25)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 shortlist must be 1..25");
    if(w==0 || h==0 || (w%block)!=0 || (h%block)!=0 || (w%2)!=0 || (h%2)!=0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 invalid dimensions");
    const auto fs=frame_size(w,h);
    if(cur.size()!=fs || prev.size()!=fs)
        throw AuroraMediaError(ErrorCode::InvalidArgument,"MC8R4 frame size mismatch");

    static const auto cand=candidates(radius);
    const auto ys=y_size(w,h);
    const auto us=uv_size(w,h);
    const auto cw=w/2;

    MotionResidual out;
    out.motion_map.reserve(static_cast<std::size_t>(w/block)*(h/block));
    out.residual_yuv420.resize(fs);

    auto residual_plane=[&](std::size_t cur_off,std::size_t prev_off,std::size_t out_off,
                            std::uint32_t stride,std::uint32_t x,std::uint32_t y,
                            std::uint32_t bs,int dx,int dy) {
        for(std::uint32_t yy=0;yy<bs;++yy) {
            const auto ci=cur_off+static_cast<std::size_t>(y+yy)*stride+x;
            const auto pi=prev_off+
                static_cast<std::size_t>(static_cast<int>(y)+dy+static_cast<int>(yy))*stride+
                static_cast<std::size_t>(static_cast<int>(x)+dx);
            const auto oi=out_off+static_cast<std::size_t>(y+yy)*stride+x;
#if defined(__SSE2__) && !defined(AURORA_DISABLE_RESIDUAL_SIMD)
            if(bs==8) {
                const __m128i a=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(cur.data()+ci));
                const __m128i b=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(prev.data()+pi));
                const __m128i d=_mm_sub_epi8(a,b);
                _mm_storel_epi64(
                    reinterpret_cast<__m128i*>(out.residual_yuv420.data()+oi),d);
                continue;
            }
#endif
            for(std::uint32_t xx=0;xx<bs;++xx) {
                const int d=static_cast<int>(cur[ci+xx])-static_cast<int>(prev[pi+xx]);
                out.residual_yuv420[oi+xx]=static_cast<Byte>(d & 0xff);
            }
        }
    };

    struct CandidateCost { std::uint32_t idx; std::uint64_t cost; };
    std::vector<CandidateCost> coarse;
    coarse.reserve(cand.size());

    for(std::uint32_t by=0;by<h;by+=block) {
        for(std::uint32_t bx=0;bx<w;bx+=block) {
            coarse.clear();
            for(std::size_t i=0;i<cand.size();++i) {
                const auto [dx,dy]=cand[i];
                const int sx=static_cast<int>(bx)+dx;
                const int sy=static_cast<int>(by)+dy;
                if(sx<0 || sy<0 || sx+static_cast<int>(block)>static_cast<int>(w) ||
                   sy+static_cast<int>(block)>static_cast<int>(h)) continue;
                std::uint64_t cost=0;
                for(std::uint32_t yy=0;yy<block;yy+=2)
                    for(std::uint32_t xx=0;xx<block;xx+=2) {
                        const auto ci=static_cast<std::size_t>(by+yy)*w+(bx+xx);
                        const auto pi=static_cast<std::size_t>(sy+static_cast<int>(yy))*w+
                                      static_cast<std::size_t>(sx+static_cast<int>(xx));
                        cost += static_cast<std::uint64_t>(
                            std::abs(static_cast<int>(cur[ci])-static_cast<int>(prev[pi])));
                    }
                coarse.push_back(CandidateCost{static_cast<std::uint32_t>(i),cost});
            }

            const auto n=std::min<std::size_t>(shortlist,coarse.size());
            std::partial_sort(coarse.begin(),coarse.begin()+static_cast<std::ptrdiff_t>(n),coarse.end(),
                [](const CandidateCost& a,const CandidateCost& b){
                    return a.cost<b.cost || (a.cost==b.cost && a.idx<b.idx);
                });

            int best_idx=-1;
            std::uint64_t best_cost=std::numeric_limits<std::uint64_t>::max();
            for(std::size_t k=0;k<n;++k) {
                const auto idx=coarse[k].idx;
                const auto [dx,dy]=cand[idx];
                const int sx=static_cast<int>(bx)+dx;
                const int sy=static_cast<int>(by)+dy;
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
                    best_idx=static_cast<int>(idx);
                }
            }

            if(best_idx<0)
                throw AuroraMediaError(ErrorCode::InternalInvariant,"MC8R4 shortlist found no candidate");

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

    static const auto cand=candidates(radius);
    const auto ys=y_size(w,h);
    const auto us=uv_size(w,h);
    const auto cw=w/2;
    Bytes out(fs);

    auto reconstruct=[&](std::size_t prev_off,std::size_t res_off,std::size_t out_off,
                         std::uint32_t stride,std::uint32_t x,std::uint32_t y,
                         std::uint32_t bs,int dx,int dy) {
        for(std::uint32_t yy=0;yy<bs;++yy) {
            const auto oi=out_off+static_cast<std::size_t>(y+yy)*stride+x;
            const auto pi=prev_off+
                static_cast<std::size_t>(static_cast<int>(y)+dy+static_cast<int>(yy))*stride+
                static_cast<std::size_t>(static_cast<int>(x)+dx);
            const auto ri=res_off+static_cast<std::size_t>(y+yy)*stride+x;
#if defined(__SSE2__) && !defined(AURORA_DISABLE_RESIDUAL_SIMD)
            if(bs==8) {
                const __m128i p=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(prev.data()+pi));
                const __m128i r=_mm_loadl_epi64(
                    reinterpret_cast<const __m128i*>(residual.data()+ri));
                const __m128i v=_mm_add_epi8(p,r);
                _mm_storel_epi64(reinterpret_cast<__m128i*>(out.data()+oi),v);
                continue;
            }
#endif
            for(std::uint32_t xx=0;xx<bs;++xx)
                out[oi+xx]=static_cast<Byte>(
                    (static_cast<unsigned>(prev[pi+xx])+residual[ri+xx])&0xffu);
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
