#include "AuroraMediaContainer.h"
#include "AuroraStreamProtocol.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora;

static std::vector<std::uint8_t> bytes(std::initializer_list<int> xs){
    std::vector<std::uint8_t> v; for(int x:xs)v.push_back(static_cast<std::uint8_t>(x)); return v;
}

int main(int argc,char** argv){
    try{
        if(argc!=3) throw std::runtime_error("usage: test_aurora_backend <python_fixture.aum> <cpp_out.aum>");
        const std::filesystem::path py=argv[1], out=argv[2];

        // Read Python-produced AUM.
        media::Demuxer d(py);
        if(d.tracks().size()!=2) throw std::runtime_error("python fixture track count");
        if(d.index().size()!=3) throw std::runtime_error("python fixture packet count");
        auto p0=d.read_packet(d.index().at(0));
        auto p1=d.read_packet(d.index().at(1));
        auto p2=d.read_packet(d.index().at(2));
        if(p0!=bytes({1,2,3,4,5}) || p1!=bytes({10,20,30}) || p2!=bytes({9,8,7,6}))
            throw std::runtime_error("python fixture payload mismatch");
        auto seek=d.seek(2,600000,true);
        if(!seek || seek->pts!=500000) throw std::runtime_error("seek mismatch");

        // Write C++ AUM for Python to validate.
        std::vector<media::Track> tracks{
            media::Track{1,media::kTrackAudio,media::kCodecAuroraAudio,0,48000,2,16,9600},
            media::Track{2,media::kTrackVideo,media::kCodecAuroraVideo,0,176,144,25,1}
        };
        {
            media::Muxer m(out,tracks);
            m.write_packet(1,0,200000,bytes({42,43,44}),media::kPacketRecovery);
            m.write_packet(2,0,800000,bytes({100,101,102,103}),media::kPacketKey|media::kPacketRecovery);
            m.write_packet(1,200000,200000,bytes({55,56}),media::kPacketRecovery);
        }

        // Native roundtrip.
        media::Demuxer d2(out);
        if(d2.index().size()!=3) throw std::runtime_error("cpp roundtrip packet count");
        if(d2.read_packet(d2.index().at(1))!=bytes({100,101,102,103}))
            throw std::runtime_error("cpp roundtrip payload");

        // Stream protocol + incremental parsing with deliberately odd chunking.
        stream::Packet sp{0,2,media::kPacketRecovery,12345,40000,bytes({7,6,5,4,3,2,1})};
        auto wire=stream::encode(sp);
        stream::IncrementalParser parser;
        parser.push(wire.data(),3);
        if(parser.pop()) throw std::runtime_error("incremental parser emitted too early");
        parser.push(wire.data()+3,11);
        if(parser.pop()) throw std::runtime_error("incremental parser emitted too early 2");
        parser.push(wire.data()+14,wire.size()-14);
        auto got=parser.pop();
        if(!got || got->payload!=sp.payload || got->pts!=sp.pts) throw std::runtime_error("incremental parse mismatch");

        stream::OrderedReceiver receiver;
        auto accepted=receiver.accept(wire);
        if(accepted.sequence!=0 || receiver.next_sequence()!=1) throw std::runtime_error("receiver sequence");

        auto corrupt=wire; corrupt.back()^=0x80;
        bool rejected=false;
        try{ (void)stream::decode(corrupt); }catch(...){ rejected=true; }
        if(!rejected) throw std::runtime_error("stream corruption not rejected");

        std::cout<<"CPP_BACKEND_PASS\n";
        std::cout<<"PY_FIXTURE_PACKETS="<<d.index().size()<<"\n";
        std::cout<<"CPP_OUTPUT_PACKETS="<<d2.index().size()<<"\n";
        return 0;
    }catch(const std::exception& e){
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
