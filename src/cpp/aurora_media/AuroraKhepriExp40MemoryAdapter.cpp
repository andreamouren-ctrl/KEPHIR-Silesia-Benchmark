#include "AuroraKhepriExp40MemoryAdapter.h"
#include "AuroraMediaError.h"
#include <cstdint>
#include <cstring>
#include <limits>

// EXP-40 shared-cache implementation is included into this translation unit so its current static
// research primitives can be reused without changing the algorithm.
// The CLI main is renamed and is not used by this adapter.
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#define main aurora_kephir_exp40_cli_main
#include "../../../KEPHIR_2_EXP40_SHARED_MATCH_CACHE.cpp"
#undef main
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

namespace aurora::media {
namespace {

constexpr std::uint8_t kFrameVersion = 1;
constexpr std::uint8_t kModeRaw = 0;
constexpr std::uint8_t kModeEncoded = 1;
constexpr std::size_t kHeaderSize = 16;
constexpr double kLit = 6.55;
constexpr double kMc = 9.42;
constexpr double kDpen = 1.20;

void put32(Bytes& out,std::uint32_t v) {
    out.push_back(static_cast<Byte>(v));
    out.push_back(static_cast<Byte>(v>>8));
    out.push_back(static_cast<Byte>(v>>16));
    out.push_back(static_cast<Byte>(v>>24));
}
std::uint32_t get32(ByteView in,std::size_t& p) {
    if(p+4>in.size()) throw AuroraMediaError(ErrorCode::TruncatedInput,"KHEPRI memory frame truncated");
    const auto v=static_cast<std::uint32_t>(in[p]) |
                 (static_cast<std::uint32_t>(in[p+1])<<8) |
                 (static_cast<std::uint32_t>(in[p+2])<<16) |
                 (static_cast<std::uint32_t>(in[p+3])<<24);
    p+=4; return v;
}

} // namespace

Bytes AuroraKhepriExp40MemoryAdapter::encode(ByteView input) {
    if(input.size()>std::numeric_limits<std::uint32_t>::max())
        throw AuroraMediaError(ErrorCode::ResourceLimit,"KHEPRI memory input too large");

    std::vector<std::uint8_t> d(input.begin(),input.end());
    std::vector<std::uint8_t> payload;
    std::uint8_t mode=kModeRaw;

    if(!d.empty()) {
        const double localDpen=k2_adaptive_dpen(d,kDpen,K2_ADAPT_MODE);
        const auto ts=parse(d,kLit,kMc,localDpen);
        std::size_t literals=0;
        for(const auto& t:ts) if(!t.dist) ++literals;

        (void)literals;
        auto encoded=::encode(d,ts);
#ifndef NO_INTERNAL_VERIFY
        if(::decode(encoded,d.size())!=d)
            throw AuroraMediaError(ErrorCode::InternalInvariant,"KHEPRI in-process internal verification failed");
#endif
        if(encoded.size()<d.size()) {
            payload=std::move(encoded);
            mode=kModeEncoded;
        } else {
            payload=d;
            mode=kModeRaw;
        }
    }

    Bytes out;
    out.reserve(kHeaderSize+payload.size());
    out.insert(out.end(),{'K','3','7','M'});
    out.push_back(kFrameVersion);
    out.push_back(mode);
    out.push_back(0);
    out.push_back(0);
    put32(out,static_cast<std::uint32_t>(d.size()));
    put32(out,static_cast<std::uint32_t>(payload.size()));
    out.insert(out.end(),payload.begin(),payload.end());
    return out;
}

Bytes AuroraKhepriExp40MemoryAdapter::decode(ByteView input) {
    if(input.size()<kHeaderSize)
        throw AuroraMediaError(ErrorCode::TruncatedInput,"KHEPRI memory frame header");
    if(input[0]!='K'||input[1]!='3'||input[2]!='7'||input[3]!='M')
        throw AuroraMediaError(ErrorCode::CorruptHeader,"KHEPRI memory frame magic");
    if(input[4]!=kFrameVersion)
        throw AuroraMediaError(ErrorCode::UnsupportedVersion,"KHEPRI memory frame version");

    const auto mode=input[5];
    std::size_t p=8;
    const auto rawSize=get32(input,p);
    const auto payloadSize=get32(input,p);
    if(p+payloadSize!=input.size())
        throw AuroraMediaError(ErrorCode::CorruptPacket,"KHEPRI memory frame size");

    std::vector<std::uint8_t> payload(input.begin()+static_cast<std::ptrdiff_t>(p),input.end());

    if(mode==kModeRaw) {
        if(payload.size()!=rawSize)
            throw AuroraMediaError(ErrorCode::CorruptPacket,"KHEPRI raw frame size");
        return Bytes(payload.begin(),payload.end());
    }
    if(mode!=kModeEncoded)
        throw AuroraMediaError(ErrorCode::CorruptPacket,"KHEPRI memory frame mode");

    try {
        auto decoded=::decode(payload,rawSize);
        if(decoded.size()!=rawSize)
            throw AuroraMediaError(ErrorCode::DecodeFailure,"KHEPRI decoded size mismatch");
        return Bytes(decoded.begin(),decoded.end());
    } catch(const AuroraMediaError&) {
        throw;
    } catch(const std::exception& e) {
        throw AuroraMediaError(ErrorCode::DecodeFailure,
                               std::string("KHEPRI in-process decode failed: ")+e.what());
    }
}

} // namespace aurora::media
