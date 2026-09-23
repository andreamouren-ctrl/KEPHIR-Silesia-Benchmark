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

    std::cout << "CODEC_INTERFACES_PASS\n";
    return 0;
}
