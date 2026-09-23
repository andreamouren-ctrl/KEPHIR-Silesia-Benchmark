#include "AuroraMediaContainer.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <unordered_set>

namespace aurora::media {
namespace {

constexpr std::array<char,4> kMagic{'A','U','M','1'};
constexpr std::array<char,4> kIndexMagic{'A','U','I','1'};
constexpr std::array<char,4> kFooterMagic{'A','U','F','1'};

template<class T>
void put_le(std::ostream& os, T v) {
    for (std::size_t i=0;i<sizeof(T);++i) {
        os.put(static_cast<char>((static_cast<std::uint64_t>(v)>>(8*i))&0xffu));
    }
    if (!os) throw AuroraMediaError(ErrorCode::IoFailure,"write failed");
}

template<class T>
T get_le(std::istream& is) {
    std::uint64_t v=0;
    for (std::size_t i=0;i<sizeof(T);++i) {
        const int c=is.get();
        if (c==EOF) throw AuroraMediaError(ErrorCode::TruncatedInput,"truncated file");
        v |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(c))<<(8*i);
    }
    return static_cast<T>(v);
}

void put_magic(std::ostream& os,const std::array<char,4>& m) {
    os.write(m.data(),4);
    if(!os) throw AuroraMediaError(ErrorCode::IoFailure,"write failed");
}
std::array<char,4> get_magic(std::istream& is) {
    std::array<char,4> x{};
    is.read(x.data(),4);
    if(is.gcount()!=4) throw AuroraMediaError(ErrorCode::TruncatedInput,"truncated magic");
    return x;
}

constexpr std::uint64_t kFileHdrSize=16;
constexpr std::uint64_t kTrackHdrSize=20;
constexpr std::uint64_t kPacketHdrSize=32;
constexpr std::uint64_t kIndexHdrSize=8;
constexpr std::uint64_t kIndexEntSize=32;
constexpr std::uint64_t kFooterSize=24;

} // namespace

std::uint32_t crc32(const std::uint8_t* data,std::size_t n) {
    std::uint32_t c=0xffffffffu;
    for(std::size_t i=0;i<n;++i) {
        c ^= data[i];
        for(int k=0;k<8;++k) c=(c>>1) ^ (0xedb88320u & (0u-(c&1u)));
    }
    return c^0xffffffffu;
}

Muxer::Muxer(const std::filesystem::path& path,std::vector<Track> tracks,
             std::uint32_t timescale, Limits limits)
: out_(path,std::ios::binary), tracks_(std::move(tracks)), timescale_(timescale), limits_(limits) {
    if(!out_) throw AuroraMediaError(ErrorCode::IoFailure,"cannot open output");
    if(tracks_.empty() || tracks_.size()>limits_.max_tracks) throw AuroraMediaError(ErrorCode::InvalidArgument,"invalid tracks");
    std::unordered_set<unsigned> ids;
    for(const auto& t:tracks_) {
        if(!ids.insert(t.id).second) throw AuroraMediaError(ErrorCode::InvalidArgument,"duplicate track id");
    }
    put_magic(out_,kMagic);
    put_le<std::uint8_t>(out_,kVersion);
    put_le<std::uint8_t>(out_,0);
    put_le<std::uint16_t>(out_,static_cast<std::uint16_t>(tracks_.size()));
    put_le<std::uint32_t>(out_,timescale_);
    put_le<std::uint32_t>(out_,0);
    for(const auto& t:tracks_) {
        put_le<std::uint8_t>(out_,t.id); put_le<std::uint8_t>(out_,t.type);
        put_le<std::uint8_t>(out_,t.codec); put_le<std::uint8_t>(out_,t.flags);
        put_le<std::uint32_t>(out_,t.p1); put_le<std::uint32_t>(out_,t.p2);
        put_le<std::uint32_t>(out_,t.p3); put_le<std::uint32_t>(out_,t.p4);
    }
}

Muxer::~Muxer() { try { close(); } catch(...) {} }

void Muxer::write_packet(std::uint8_t track_id,std::uint64_t pts,
                         std::uint64_t duration,
                         const std::vector<std::uint8_t>& payload,
                         std::uint8_t flags) {
    if(closed_) throw AuroraMediaError(ErrorCode::InvalidArgument,"muxer closed");
    if(std::none_of(tracks_.begin(),tracks_.end(),[&](const Track& t){return t.id==track_id;}))
        throw AuroraMediaError(ErrorCode::InvalidArgument,"unknown track");
    if(payload.size()>std::numeric_limits<std::uint32_t>::max() || payload.size()>limits_.max_packet_bytes)
        throw AuroraMediaError(ErrorCode::ResourceLimit,"payload too large");

    const auto off=static_cast<std::uint64_t>(out_.tellp());
    const auto crc=crc32(payload.data(),payload.size());
    put_le<std::uint8_t>(out_,track_id); put_le<std::uint8_t>(out_,flags);
    put_le<std::uint16_t>(out_,0); put_le<std::uint64_t>(out_,pts);
    put_le<std::uint64_t>(out_,duration);
    put_le<std::uint32_t>(out_,static_cast<std::uint32_t>(payload.size()));
    put_le<std::uint32_t>(out_,crc); put_le<std::uint32_t>(out_,0);
    if(!payload.empty()) out_.write(reinterpret_cast<const char*>(payload.data()),static_cast<std::streamsize>(payload.size()));
    if(!out_) throw AuroraMediaError(ErrorCode::IoFailure,"payload write failed");
    index_.push_back(PacketInfo{track_id,flags,pts,duration,off,static_cast<std::uint32_t>(payload.size())});
}

void Muxer::close() {
    if(closed_) return;
    const auto idx_off=static_cast<std::uint64_t>(out_.tellp());

    std::vector<std::uint8_t> ib;
    auto append=[&](auto v) {
        using T=decltype(v);
        for(std::size_t i=0;i<sizeof(T);++i)
            ib.push_back(static_cast<std::uint8_t>((static_cast<std::uint64_t>(v)>>(8*i))&0xffu));
    };
    ib.insert(ib.end(),kIndexMagic.begin(),kIndexMagic.end());
    append(static_cast<std::uint32_t>(index_.size()));
    for(const auto& e:index_) {
        append(e.track_id); append(e.flags); append(static_cast<std::uint16_t>(0));
        append(e.pts); append(e.duration); append(e.file_offset); append(e.size);
    }
    if(!ib.empty()) out_.write(reinterpret_cast<const char*>(ib.data()),static_cast<std::streamsize>(ib.size()));
    put_magic(out_,kFooterMagic);
    put_le<std::uint64_t>(out_,idx_off);
    put_le<std::uint64_t>(out_,static_cast<std::uint64_t>(ib.size()));
    put_le<std::uint32_t>(out_,crc32(ib.data(),ib.size()));
    out_.close();
    closed_=true;
}

Demuxer::Demuxer(const std::filesystem::path& path, Limits limits):in_(path,std::ios::binary), limits_(limits) {
    if(!in_) throw AuroraMediaError(ErrorCode::IoFailure,"cannot open input");
    read_header_and_tracks();
    read_index();
}

void Demuxer::read_header_and_tracks() {
    if(get_magic(in_)!=kMagic) throw AuroraMediaError(ErrorCode::CorruptHeader,"bad AURORA Media magic");
    const auto ver=get_le<std::uint8_t>(in_);
    (void)get_le<std::uint8_t>(in_);
    const auto n=get_le<std::uint16_t>(in_);
    timescale_=get_le<std::uint32_t>(in_);
    (void)get_le<std::uint32_t>(in_);
    if(ver!=kVersion || n==0 || n>limits_.max_tracks) throw AuroraMediaError(ErrorCode::UnsupportedVersion,"unsupported header");
    std::unordered_set<unsigned> ids;
    for(std::uint16_t i=0;i<n;++i) {
        Track t{};
        t.id=get_le<std::uint8_t>(in_); t.type=get_le<std::uint8_t>(in_);
        t.codec=get_le<std::uint8_t>(in_); t.flags=get_le<std::uint8_t>(in_);
        t.p1=get_le<std::uint32_t>(in_);t.p2=get_le<std::uint32_t>(in_);
        t.p3=get_le<std::uint32_t>(in_);t.p4=get_le<std::uint32_t>(in_);
        if(!ids.insert(t.id).second) throw AuroraMediaError(ErrorCode::CorruptHeader,"duplicate track id");
        tracks_.push_back(t);
    }
    data_start_=static_cast<std::uint64_t>(in_.tellg());
}

void Demuxer::read_index() {
    in_.seekg(0,std::ios::end);
    const auto end=static_cast<std::uint64_t>(in_.tellg());
    if(end<kFooterSize) throw AuroraMediaError(ErrorCode::TruncatedInput,"missing footer");
    in_.seekg(static_cast<std::streamoff>(end-kFooterSize));
    if(get_magic(in_)!=kFooterMagic) throw AuroraMediaError(ErrorCode::CorruptIndex,"bad footer magic");
    const auto off=get_le<std::uint64_t>(in_);
    const auto sz=get_le<std::uint64_t>(in_);
    const auto expected_crc=get_le<std::uint32_t>(in_);
    if(off<data_start_ || off+sz>end-kFooterSize || sz<kIndexHdrSize || sz>limits_.max_index_bytes)
        throw AuroraMediaError(ErrorCode::CorruptIndex,"bad index bounds");

    in_.seekg(static_cast<std::streamoff>(off));
    std::vector<std::uint8_t> b(static_cast<std::size_t>(sz));
    in_.read(reinterpret_cast<char*>(b.data()),static_cast<std::streamsize>(b.size()));
    if(static_cast<std::size_t>(in_.gcount())!=b.size()) throw AuroraMediaError(ErrorCode::TruncatedInput,"truncated index");
    if(crc32(b.data(),b.size())!=expected_crc) throw AuroraMediaError(ErrorCode::CrcMismatch,"index CRC");

    std::size_t p=0;
    auto get8=[&](){ if(p+1>b.size()) throw AuroraMediaError(ErrorCode::TruncatedInput,"index truncated"); return b[p++]; };
    auto get16=[&](){ std::uint16_t v=0; for(int i=0;i<2;++i)v|=std::uint16_t(get8())<<(8*i);return v; };
    auto get32=[&](){ std::uint32_t v=0; for(int i=0;i<4;++i)v|=std::uint32_t(get8())<<(8*i);return v; };
    auto get64=[&](){ std::uint64_t v=0; for(int i=0;i<8;++i)v|=std::uint64_t(get8())<<(8*i);return v; };

    for(char c:kIndexMagic) if(get8()!=static_cast<std::uint8_t>(c)) throw AuroraMediaError(ErrorCode::CorruptIndex,"bad index magic");
    const auto count=get32();
    if(count>limits_.max_index_entries) throw AuroraMediaError(ErrorCode::ResourceLimit,"index entry limit");
    if(kIndexHdrSize+static_cast<std::uint64_t>(count)*kIndexEntSize!=sz)
        throw AuroraMediaError(ErrorCode::CorruptIndex,"index size mismatch");
    index_.reserve(count);
    for(std::uint32_t i=0;i<count;++i) {
        PacketInfo e{};
        e.track_id=get8(); e.flags=get8(); (void)get16();
        e.pts=get64(); e.duration=get64(); e.file_offset=get64(); e.size=get32();
        if(e.size>limits_.max_packet_bytes) throw AuroraMediaError(ErrorCode::ResourceLimit,"packet size limit");
        if(e.file_offset<data_start_ || e.file_offset+kPacketHdrSize+e.size>off)
            throw AuroraMediaError(ErrorCode::CorruptIndex,"packet index bounds");
        index_.push_back(e);
    }
}

std::vector<std::uint8_t> Demuxer::read_packet(const PacketInfo& e) {
    in_.clear(); in_.seekg(static_cast<std::streamoff>(e.file_offset));
    const auto tid=get_le<std::uint8_t>(in_); const auto flags=get_le<std::uint8_t>(in_);
    (void)get_le<std::uint16_t>(in_); const auto pts=get_le<std::uint64_t>(in_);
    const auto dur=get_le<std::uint64_t>(in_); const auto sz=get_le<std::uint32_t>(in_);
    if(sz>limits_.max_packet_bytes) throw AuroraMediaError(ErrorCode::ResourceLimit,"packet size limit");
    const auto expected_crc=get_le<std::uint32_t>(in_); (void)get_le<std::uint32_t>(in_);
    if(tid!=e.track_id||flags!=e.flags||pts!=e.pts||dur!=e.duration||sz!=e.size)
        throw AuroraMediaError(ErrorCode::CorruptPacket,"packet/index mismatch");
    std::vector<std::uint8_t> p(sz);
    if(sz) in_.read(reinterpret_cast<char*>(p.data()),sz);
    if(static_cast<std::size_t>(in_.gcount())!=sz && sz) throw AuroraMediaError(ErrorCode::TruncatedInput,"truncated packet");
    if(crc32(p.data(),p.size())!=expected_crc) throw AuroraMediaError(ErrorCode::CrcMismatch,"packet CRC");
    return p;
}

std::optional<PacketInfo> Demuxer::seek(std::uint8_t track_id,std::uint64_t pts,bool recovery_only) const {
    std::optional<PacketInfo> best;
    for(const auto& e:index_) {
        if(e.track_id!=track_id || e.pts>pts) continue;
        if(recovery_only && !(e.flags&(kPacketKey|kPacketRecovery))) continue;
        if(!best || e.pts>best->pts) best=e;
    }
    return best;
}

} // namespace aurora::media
