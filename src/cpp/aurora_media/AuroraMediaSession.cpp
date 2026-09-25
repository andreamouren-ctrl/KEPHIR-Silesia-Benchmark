#include "AuroraMediaSession.h"
#include <algorithm>
#include <stdexcept>
#include <unordered_set>
#include <unordered_map>

namespace aurora::media {

MediaSession::MediaSession(const std::filesystem::path& path):demux_(path) {
    validate_tracks();
    build_order();
}

void MediaSession::validate_tracks() {
    bool has_audio=false,has_video=false;
    for(const auto& t:demux_.tracks()) {
        if(t.type==kTrackAudio) {
            if(t.codec!=kCodecAuroraAudio) throw std::runtime_error("unsupported audio codec");
            (void)audio_format_from_track(t);
            has_audio=true;
        } else if(t.type==kTrackVideo) {
            if(t.codec!=kCodecAuroraVideo) throw std::runtime_error("unsupported video codec");
            if(t.p1==0 || t.p2==0 || t.p3==0 || t.p4==0) throw std::runtime_error("invalid video track parameters");
            has_video=true;
        } else {
            throw std::runtime_error("unsupported track type");
        }
    }
    if(!has_audio && !has_video) throw std::runtime_error("no media tracks");
}

void MediaSession::build_order() {
    order_=demux_.index();
    std::stable_sort(order_.begin(),order_.end(),[](const PacketInfo& a,const PacketInfo& b){
        if(a.pts!=b.pts) return a.pts<b.pts;
        return a.track_id<b.track_id;
    });

    // Enforce monotonic PTS within each track.
    std::unordered_map<unsigned,std::uint64_t> last;
    std::unordered_set<unsigned> seen;
    for(const auto& e:order_) {
        const unsigned id=e.track_id;
        if(seen.contains(id) && e.pts<last[id]) throw std::runtime_error("non-monotonic track PTS");
        last[id]=e.pts; seen.insert(id);
    }
}

std::optional<Track> MediaSession::audio_track() const {
    for(const auto& t:demux_.tracks()) if(t.type==kTrackAudio) return t;
    return std::nullopt;
}
std::optional<AudioFormat> MediaSession::audio_format() const {
    auto t=audio_track();
    if(!t) return std::nullopt;
    return audio_format_from_track(*t);
}
std::optional<Track> MediaSession::video_track() const {
    for(const auto& t:demux_.tracks()) if(t.type==kTrackVideo) return t;
    return std::nullopt;
}

void MediaSession::reset(){ cursor_=0; }

std::optional<TimedPacket> MediaSession::next() {
    if(cursor_>=order_.size()) return std::nullopt;
    const auto e=order_[cursor_++];
    return TimedPacket{e,demux_.read_packet(e)};
}

std::uint64_t MediaSession::seek(std::uint64_t requested_pts) {
    std::optional<PacketInfo> anchor;
    auto v=video_track();
    if(v) anchor=demux_.seek(v->id,requested_pts,true);
    if(!anchor) {
        auto a=audio_track();
        if(a) anchor=demux_.seek(a->id,requested_pts,true);
    }
    const std::uint64_t start=anchor ? anchor->pts : 0;
    cursor_=static_cast<std::size_t>(std::lower_bound(order_.begin(),order_.end(),start,
        [](const PacketInfo& e,std::uint64_t pts){return e.pts<pts;})-order_.begin());
    return start;
}

} // namespace aurora::media
