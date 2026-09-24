#include "AuroraCodecInterfaces.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

class EchoKhepri final : public IKhepriBackend {
public:
    Bytes encode(ByteView input) override { return Bytes(input.begin(), input.end()); }
    Bytes decode(ByteView input) override { return Bytes(input.begin(), input.end()); }
};

class AudioPass final : public IAudioEncoder, public IAudioDecoder {
public:
    explicit AudioPass(IKhepriBackend& backend) : backend_(backend) {}
    EncodedPacket encode(ByteView pcm) override {
        return EncodedPacket{backend_.encode(pcm), false, true};
    }
    Bytes decode(ByteView payload) override { return backend_.decode(payload); }
private:
    IKhepriBackend& backend_;
};

class VideoPass final : public IVideoEncoder, public IVideoDecoder {
public:
    explicit VideoPass(IKhepriBackend& backend) : backend_(backend) {}
    EncodedPacket encode(ByteView yuv) override {
        return EncodedPacket{backend_.encode(yuv), true, true};
    }
    Bytes decode(ByteView payload) override { return backend_.decode(payload); }
private:
    IKhepriBackend& backend_;
};

int main() {
    EchoKhepri backend;
    AudioPass audio(backend);
    VideoPass video(backend);

    const Bytes a{1,2,3,4,5};
    const auto ae=audio.encode(a);
    if(!ae.recovery || ae.key || audio.decode(ae.payload)!=a)
        throw std::runtime_error("audio interface failure");

    const Bytes v{9,8,7,6};
    const auto ve=video.encode(v);
    if(!ve.recovery || !ve.key || video.decode(ve.payload)!=v)
        throw std::runtime_error("video interface failure");

    const AudioEncodeConfig ac{};
    const VideoEncodeConfig vc{};
    if(ac.format.sample_rate!=48'000 || vc.routing_horizon_frames!=20)
        throw std::runtime_error("default configuration failure");

    // Resolution-agnostic SDR geometries.
    for(const auto& f : std::vector<VideoFormat>{
            VideoFormat{640,480,25,1,8,ChromaFormat::Yuv420},
            VideoFormat{1280,720,60,1,8,ChromaFormat::Yuv420},
            VideoFormat{1920,1080,60,1,8,ChromaFormat::Yuv420},
            VideoFormat{2560,1440,60,1,10,ChromaFormat::Yuv422},
            VideoFormat{3840,2160,60,1,10,ChromaFormat::Yuv420},
            VideoFormat{7680,4320,60,1,10,ChromaFormat::Yuv420},
            VideoFormat{4096,1716,24,1,12,ChromaFormat::Yuv444}}) {
        validate_video_format(f);
    }

    VideoFormat hdr10{3840,2160,60,1,10,ChromaFormat::Yuv420,
                      ColorPrimaries::Bt2020,TransferCharacteristics::PqSt2084,
                      MatrixCoefficients::Bt2020Ncl,ColorRange::Limited,
                      HdrStaticMetadata{true,1000,400,50,1000}};
    validate_video_format(hdr10);
    if(!is_hdr(hdr10)) throw std::runtime_error("HDR10 detection failure");

    VideoFormat hlg{1920,1080,50,1,10,ChromaFormat::Yuv422,
                    ColorPrimaries::Bt2020,TransferCharacteristics::Hlg,
                    MatrixCoefficients::Bt2020Ncl,ColorRange::Limited,{}};
    validate_video_format(hlg);

    bool rejected=false;
    try {
        auto bad=hdr10;
        bad.bit_depth=8;
        validate_video_format(bad);
    } catch(const AuroraMediaError&) { rejected=true; }
    if(!rejected) throw std::runtime_error("8-bit HDR must be rejected");

    rejected=false;
    try {
        VideoFormat bad{1919,1080,30,1,8,ChromaFormat::Yuv420};
        validate_video_format(bad);
    } catch(const AuroraMediaError&) { rejected=true; }
    if(!rejected) throw std::runtime_error("odd-width YUV420 must be rejected");

    std::cout << "VIDEO_FORMATS_PASS resolutions=7 hdr10=1 hlg=1 bitdepths=8,10,12\n";
    std::cout << "CODEC_INTERFACES_PASS\n";
    return 0;
}
