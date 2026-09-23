#include "AuroraMediaContainer.h"
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

static std::vector<std::uint8_t> read_all(const std::filesystem::path& p) {
    std::ifstream f(p,std::ios::binary);
    return std::vector<std::uint8_t>((std::istreambuf_iterator<char>(f)),{});
}
static void write_all(const std::filesystem::path& p,const std::vector<std::uint8_t>& b) {
    std::ofstream f(p,std::ios::binary);
    f.write(reinterpret_cast<const char*>(b.data()),static_cast<std::streamsize>(b.size()));
}
template<class F>
static bool rejects(F&& f) {
    try { f(); } catch (...) { return true; }
    return false;
}

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: test_aurora_corruption_matrix <dir>");
        const std::filesystem::path dir=argv[1];
        std::filesystem::create_directories(dir);
        const auto good=dir/"good.aum";

        std::vector<Track> tracks{
            {1,kTrackAudio,kCodecAuroraAudio,0,48000,2,16,9600},
            {2,kTrackVideo,kCodecAuroraVideo,0,176,144,25,1}
        };
        {
            Muxer m(good,tracks);
            m.write_packet(1,0,200000,{1,2,3,4,5,6},kPacketRecovery);
            m.write_packet(2,0,400000,{9,8,7,6,5,4,3},kPacketKey|kPacketRecovery);
        }

        const auto src=read_all(good);
        if(src.size()<160) throw std::runtime_error("fixture unexpectedly small");

        std::size_t cases=0;
        auto expect_bad=[&](const char* name,std::vector<std::uint8_t> b, bool read_packet=false){
            const auto p=dir/(std::string(name)+".aum");
            write_all(p,b);
            const bool bad=rejects([&]{
                Demuxer d(p);
                if(read_packet) {
                    for(const auto& e:d.index()) (void)d.read_packet(e);
                }
            });
            if(!bad) throw std::runtime_error(std::string("corruption accepted: ")+name);
            ++cases;
        };

        {
            auto b=src; b[0]^=0x40; expect_bad("bad_file_magic",std::move(b));
        }
        {
            auto b=src; b[4]=0xff; expect_bad("bad_version",std::move(b));
        }
        {
            auto b=src; b.resize(10); expect_bad("truncated_header",std::move(b));
        }
        {
            auto b=src; b.resize(b.size()-1); expect_bad("truncated_footer",std::move(b));
        }
        {
            auto b=src; b[b.size()-24]^=0x20; expect_bad("bad_footer_magic",std::move(b));
        }
        {
            auto b=src; b[b.size()-1]^=0x01; expect_bad("bad_index_crc",std::move(b));
        }
        {
            // First payload begins after 16-byte file header + 2*20-byte track headers + 32-byte packet header.
            auto b=src;
            constexpr std::size_t first_payload=16+2*20+32;
            b[first_payload]^=0x80;
            expect_bad("bad_packet_crc",std::move(b),true);
        }
        {
            auto b=src;
            // Damage first packet's recorded payload size in its packet header.
            constexpr std::size_t first_packet=16+2*20;
            constexpr std::size_t size_offset=1+1+2+8+8;
            b[first_packet+size_offset]^=0x10;
            expect_bad("packet_index_mismatch",std::move(b),true);
        }

        // Good file must still parse and validate.
        {
            Demuxer d(good);
            if(d.index().size()!=2) throw std::runtime_error("good fixture index");
            for(const auto& e:d.index()) (void)d.read_packet(e);
        }

        std::cout<<"CORRUPTION_MATRIX_PASS cases="<<cases<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
