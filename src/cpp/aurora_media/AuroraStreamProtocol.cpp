#include "AuroraStreamProtocol.h"
#include "AuroraMediaContainer.h"
#include <array>
#include <stdexcept>

namespace aurora::stream {
namespace {
constexpr std::array<std::uint8_t,4> magic{'A','U','S','1'};
constexpr std::uint8_t version=1;
constexpr std::size_t header_size=40;

template<class T>
void append(std::vector<std::uint8_t>& b,T v){
    for(std::size_t i=0;i<sizeof(T);++i)b.push_back(static_cast<std::uint8_t>((static_cast<std::uint64_t>(v)>>(8*i))&0xff));
}
template<class T>
T read(const std::vector<std::uint8_t>& b,std::size_t& p){
    if(p+sizeof(T)>b.size()) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::TruncatedInput,"truncated stream packet");
    std::uint64_t v=0; for(std::size_t i=0;i<sizeof(T);++i)v|=std::uint64_t(b[p++])<<(8*i);
    return static_cast<T>(v);
}
}

std::vector<std::uint8_t> encode(const Packet& p){
    std::vector<std::uint8_t> b; b.reserve(header_size+p.payload.size());
    b.insert(b.end(),magic.begin(),magic.end()); append(b,version); append(b,p.track_id);
    append(b,p.flags); append(b,std::uint8_t{0}); append(b,p.sequence);
    append(b,p.pts); append(b,p.duration); append(b,static_cast<std::uint32_t>(p.payload.size()));
    append(b,aurora::media::crc32(p.payload.data(),p.payload.size())); append(b,std::uint32_t{0});
    b.insert(b.end(),p.payload.begin(),p.payload.end()); return b;
}

Packet decode(const std::vector<std::uint8_t>& b){
    if(b.size()<header_size) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::TruncatedInput,"truncated stream packet");
    std::size_t p=0; for(auto m:magic) if(read<std::uint8_t>(b,p)!=m) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::CorruptHeader,"bad stream magic");
    if(read<std::uint8_t>(b,p)!=version) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::UnsupportedVersion,"bad stream version");
    Packet out; out.track_id=read<std::uint8_t>(b,p);out.flags=read<std::uint8_t>(b,p);(void)read<std::uint8_t>(b,p);
    out.sequence=read<std::uint32_t>(b,p);out.pts=read<std::uint64_t>(b,p);out.duration=read<std::uint64_t>(b,p);
    const auto sz=read<std::uint32_t>(b,p);const auto crc=read<std::uint32_t>(b,p);(void)read<std::uint32_t>(b,p);
    if(sz>aurora::media::kDefaultLimits.max_packet_bytes) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::ResourceLimit,"stream packet size limit");
    if(b.size()!=header_size+sz) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::CorruptPacket,"stream size mismatch");
    out.payload.assign(b.begin()+static_cast<std::ptrdiff_t>(p),b.end());
    if(aurora::media::crc32(out.payload.data(),out.payload.size())!=crc) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::CrcMismatch,"stream CRC");
    return out;
}

void IncrementalParser::push(const std::uint8_t* data,std::size_t n){
    if(n>max_buffer_bytes_ || buffer_.size()>max_buffer_bytes_-n)
        throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::ResourceLimit,"stream buffer limit");
    buffer_.insert(buffer_.end(),data,data+n);
}
std::optional<Packet> IncrementalParser::pop(){
    if(buffer_.size()<header_size) return std::nullopt;
    std::size_t p=28; // size field offset in AUS1 v1
    std::uint32_t sz=0;for(int i=0;i<4;++i)sz|=std::uint32_t(buffer_[p+i])<<(8*i);
    if(sz>aurora::media::kDefaultLimits.max_packet_bytes) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::ResourceLimit,"stream packet size limit");
    const std::size_t total=header_size+sz;
    if(buffer_.size()<total) return std::nullopt;
    std::vector<std::uint8_t> one(buffer_.begin(),buffer_.begin()+static_cast<std::ptrdiff_t>(total));
    buffer_.erase(buffer_.begin(),buffer_.begin()+static_cast<std::ptrdiff_t>(total));
    return decode(one);
}
Packet OrderedReceiver::accept(const std::vector<std::uint8_t>& wire){
    auto p=decode(wire);
    if(p.sequence!=next_) throw aurora::media::AuroraMediaError(aurora::media::ErrorCode::SequenceGap,"stream sequence gap");
    ++next_; return p;
}

} // namespace aurora::stream
