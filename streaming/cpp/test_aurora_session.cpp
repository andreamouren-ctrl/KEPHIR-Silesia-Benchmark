#include "AuroraMediaContainer.h"
#include "AuroraMediaSession.h"
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

static std::vector<std::uint8_t> b(std::initializer_list<int> xs){
    std::vector<std::uint8_t> v;for(auto x:xs)v.push_back(static_cast<std::uint8_t>(x));return v;
}

int main(int argc,char** argv){
    try{
        if(argc!=2) throw std::runtime_error("usage: test_aurora_session <out.aum>");
        std::filesystem::path p=argv[1];
        std::vector<Track> tracks{
          Track{1,kTrackAudio,kCodecAuroraAudio,0,48000,2,16,9600},
          Track{2,kTrackVideo,kCodecAuroraVideo,0,176,144,25,1}
        };
        {
            Muxer m(p,tracks);
            m.write_packet(1,0,200000,b({1}),kPacketRecovery);
            m.write_packet(2,0,800000,b({2}),kPacketKey|kPacketRecovery);
            m.write_packet(1,200000,200000,b({3}),kPacketRecovery);
            m.write_packet(1,400000,200000,b({4}),kPacketRecovery);
            m.write_packet(1,600000,200000,b({5}),kPacketRecovery);
            m.write_packet(2,800000,800000,b({6}),kPacketKey|kPacketRecovery);
            m.write_packet(1,800000,200000,b({7}),kPacketRecovery);
        }

        MediaSession s(p);
        if(!s.audio_track()||!s.video_track()) throw std::runtime_error("tracks missing");
        if(s.packet_count()!=7) throw std::runtime_error("packet count");

        std::vector<unsigned> seen;
        while(auto x=s.next()) seen.push_back(x->payload.at(0));
        if(seen!=std::vector<unsigned>({1,2,3,4,5,7,6}))
            throw std::runtime_error("timeline order");

        auto start=s.seek(950000);
        if(start!=800000) throw std::runtime_error("seek anchor");
        auto first=s.next();
        if(!first || first->info.pts!=800000) throw std::runtime_error("seek cursor");

        s.reset();
        if(s.cursor()!=0) throw std::runtime_error("reset");

        std::cout<<"MEDIA_SESSION_PASS\n";
        return 0;
    }catch(const std::exception& e){
        std::cerr<<"FAIL: "<<e.what()<<"\n"; return 1;
    }
}
