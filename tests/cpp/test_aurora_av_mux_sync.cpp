#include "AuroraMediaContainer.h"
#include "AuroraMediaSession.h"
#include "AuroraMediaTiming.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: aurora_av_mux_sync_test <out.aum>");

        constexpr std::uint32_t ts=1'000'000;
        constexpr std::uint32_t sample_rate=48'000;
        constexpr std::uint32_t fps_num=30'000;
        constexpr std::uint32_t fps_den=1'001;
        constexpr std::uint64_t duration_s=600;
        constexpr std::uint64_t audio_packet_samples=960; // 20 ms
        constexpr std::uint64_t audio_packets=duration_s*sample_rate/audio_packet_samples;
        constexpr std::uint64_t video_frames=duration_s*fps_num/fps_den;
        constexpr std::uint64_t video_recovery_interval=30;

        const std::filesystem::path path=argv[1];
        const std::vector<Track> tracks{
            Track{1,kTrackAudio,kCodecAuroraAudio,0,sample_rate,2,16,
                  static_cast<std::uint32_t>(audio_packet_samples)},
            Track{2,kTrackVideo,kCodecAuroraVideo,0,1920,1080,fps_num,fps_den}
        };

        {
            Muxer mux(path,tracks,ts);
            std::uint64_t ai=0,vi=0;
            while(ai<audio_packets || vi<video_frames) {
                const auto apts = ai<audio_packets
                    ? audio_pts(ai*audio_packet_samples,sample_rate,ts)
                    : std::numeric_limits<std::uint64_t>::max();
                const auto vpts = vi<video_frames
                    ? video_pts(vi,fps_num,fps_den,ts)
                    : std::numeric_limits<std::uint64_t>::max();

                if(apts<=vpts) {
                    const auto anext=audio_pts((ai+1)*audio_packet_samples,sample_rate,ts);
                    mux.write_packet(1,apts,anext-apts,
                                     {static_cast<Byte>(ai&0xffu)},kPacketRecovery);
                    ++ai;
                } else {
                    const auto vnext=video_pts(vi+1,fps_num,fps_den,ts);
                    const bool recovery=(vi%video_recovery_interval)==0;
                    mux.write_packet(2,vpts,vnext-vpts,
                                     {static_cast<Byte>(vi&0xffu)},
                                     recovery ? (kPacketKey|kPacketRecovery) : 0);
                    ++vi;
                }
            }
        }

        MediaSession session(path);
        if(session.timescale()!=ts) throw std::runtime_error("timescale mismatch");
        if(!session.audio_track() || !session.video_track())
            throw std::runtime_error("missing A/V tracks");
        if(session.packet_count()!=audio_packets+video_frames)
            throw std::runtime_error("muxed packet count mismatch");

        std::uint64_t last_global_pts=0;
        bool first=true;
        std::uint64_t audio_count=0,video_count=0;
        std::uint64_t last_audio_end=0,last_video_end=0;
        double worst_alignment_ms=0.0;

        while(auto pkt=session.next()) {
            if(!first && pkt->info.pts<last_global_pts)
                throw std::runtime_error("demux timeline order regression");
            first=false;
            last_global_pts=pkt->info.pts;

            if(pkt->info.track_id==1) {
                ++audio_count;
                last_audio_end=pkt->info.pts+pkt->info.duration;
            } else if(pkt->info.track_id==2) {
                ++video_count;
                last_video_end=pkt->info.pts+pkt->info.duration;

                const long double sample_pos=
                    static_cast<long double>(pkt->info.pts)*sample_rate/ts;
                const auto nearest_audio_packet=static_cast<std::uint64_t>(
                    std::llround(sample_pos/audio_packet_samples));
                const auto nearest_audio_pts=audio_pts(
                    nearest_audio_packet*audio_packet_samples,sample_rate,ts);
                const auto delta=pkt->info.pts>nearest_audio_pts
                    ? pkt->info.pts-nearest_audio_pts
                    : nearest_audio_pts-pkt->info.pts;
                worst_alignment_ms=std::max(
                    worst_alignment_ms,static_cast<double>(delta)*1000.0/ts);
            }
        }

        if(audio_count!=audio_packets || video_count!=video_frames)
            throw std::runtime_error("demux packet counts changed");
        if(last_audio_end!=duration_s*ts)
            throw std::runtime_error("audio end drift after mux/demux");

        const auto expected_video_end=video_pts(video_frames,fps_num,fps_den,ts);
        if(last_video_end!=expected_video_end)
            throw std::runtime_error("video end drift after mux/demux");
        if(worst_alignment_ms>10.001)
            throw std::runtime_error("mux/demux A/V alignment exceeds 10 ms");

        const std::uint64_t seek_target=300*ts+123456;
        const auto seek_start=session.seek(seek_target);
        if(seek_start>seek_target)
            throw std::runtime_error("seek moved after requested PTS");
        if(seek_target-seek_start>1'100'000)
            throw std::runtime_error("seek recovery anchor too far away");

        auto first_after_seek=session.next();
        if(!first_after_seek || first_after_seek->info.pts<seek_start)
            throw std::runtime_error("seek cursor invalid");

        std::cout<<"AV_MUX_SYNC_PASS"
                 <<" duration_s="<<duration_s
                 <<" fps=30000/1001"
                 <<" audio_packets="<<audio_count
                 <<" video_frames="<<video_count
                 <<" worst_alignment_ms="<<worst_alignment_ms
                 <<" audio_end_pts="<<last_audio_end
                 <<" video_end_pts="<<last_video_end
                 <<" seek_error_ms="<<static_cast<double>(seek_target-seek_start)/1000.0
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
