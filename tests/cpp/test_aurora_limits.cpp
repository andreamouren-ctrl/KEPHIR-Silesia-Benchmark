#include "AuroraCodecInterfaces.h"
#include "AuroraMediaContainer.h"
#include "AuroraMediaLimits.h"
#include "AuroraStreamProtocol.h"
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora;

template<class F>
static bool rejects(F&& f) {
    try { f(); } catch (...) { return true; }
    return false;
}

int main(int argc, char** argv) {
    try {
        if(argc != 2) throw std::runtime_error("usage: test_aurora_limits <tmp.aum>");
        const std::filesystem::path tmp = argv[1];

        media::Limits tiny = media::kDefaultLimits;
        tiny.max_tracks = 1;
        if(!rejects([&]{
            std::vector<media::Track> tracks{
                {1,media::kTrackAudio,media::kCodecAuroraAudio,0,48000,2,16,9600},
                {2,media::kTrackVideo,media::kCodecAuroraVideo,0,176,144,25,1}
            };
            media::Muxer m(tmp, tracks, media::kDefaultTimescale, tiny);
        })) throw std::runtime_error("track limit not enforced");

        media::Limits packet_limit = media::kDefaultLimits;
        packet_limit.max_packet_bytes = 4;
        {
            std::vector<media::Track> tracks{
                {1,media::kTrackAudio,media::kCodecAuroraAudio,0,48000,2,16,9600}
            };
            media::Muxer m(tmp, tracks, media::kDefaultTimescale, packet_limit);
            if(!rejects([&]{
                m.write_packet(1,0,1000,std::vector<std::uint8_t>{1,2,3,4,5},media::kPacketRecovery);
            })) throw std::runtime_error("packet write limit not enforced");
            m.write_packet(1,0,1000,std::vector<std::uint8_t>{1,2,3,4},media::kPacketRecovery);
            m.close();
        }

        if(!rejects([&]{
            media::Limits read_limit = media::kDefaultLimits;
            read_limit.max_packet_bytes = 3;
            media::Demuxer d(tmp, read_limit);
            (void)d;
        })) throw std::runtime_error("packet read limit not enforced");

        stream::IncrementalParser parser(8);
        const std::vector<std::uint8_t> too_much(9,0);
        if(!rejects([&]{ parser.push(too_much); }))
            throw std::runtime_error("stream buffer limit not enforced");

        std::cout << "RESOURCE_LIMITS_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << "\n";
        return 1;
    }
}
