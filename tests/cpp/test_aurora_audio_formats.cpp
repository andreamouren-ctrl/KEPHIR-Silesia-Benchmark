#include "AuroraAudioFormat.h"
#include "AuroraMediaContainer.h"
#include "AuroraMediaSession.h"
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace aurora::media;

struct Case {
    const char* name;
    AudioFormat format;
};

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: test_aurora_audio_formats <out-dir>");
        const std::filesystem::path root=argv[1];
        std::filesystem::create_directories(root);

        const std::vector<Case> cases{
            {"mono24_44100",  {44100,1,24,AudioChannelLayout::Mono,4410}},
            {"stereo16_48000",{48000,2,16,AudioChannelLayout::Stereo,9600}},
            {"surround51_24", {96000,6,24,AudioChannelLayout::Surround51,9600}},
            {"surround71_32", {192000,8,32,AudioChannelLayout::Surround71,19200}},
            {"custom12_32",   {384000,12,32,AudioChannelLayout::Custom,38400}},
            {"custom32_24",   {768000,32,24,AudioChannelLayout::Custom,76800}}
        };

        for(std::size_t i=0;i<cases.size();++i) {
            const auto& c=cases[i];
            const auto p=root/(std::string(c.name)+".aum");
            {
                Muxer m(p,{make_audio_track(1,c.format)});
                m.write_packet(1,0,1000,{1,2,3,4},kPacketRecovery);
            }
            MediaSession s(p);
            const auto got=s.audio_format();
            if(!got) throw std::runtime_error("audio format missing");
            if(got->sample_rate!=c.format.sample_rate ||
               got->channels!=c.format.channels ||
               got->bits_per_sample!=c.format.bits_per_sample ||
               got->layout!=c.format.layout ||
               got->recovery_frames!=c.format.recovery_frames)
                throw std::runtime_error("audio format roundtrip mismatch");
        }

        bool rejected=false;
        try {
            AudioFormat bad{48000,6,24,AudioChannelLayout::Stereo,4800};
            (void)make_audio_track(7,bad);
        } catch(const std::exception&) { rejected=true; }
        if(!rejected) throw std::runtime_error("layout mismatch was accepted");

        rejected=false;
        try {
            AudioFormat bad{48000,2,20,AudioChannelLayout::Stereo,4800};
            (void)make_audio_track(7,bad);
        } catch(const std::exception&) { rejected=true; }
        if(!rejected) throw std::runtime_error("unsupported bit depth was accepted");

        std::cout<<"AUDIO_FORMAT_MATRIX_PASS cases="<<cases.size()
                 <<" bits=16,24,32 channels=1..32 max_rate=768000 lossless_metadata=1\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
