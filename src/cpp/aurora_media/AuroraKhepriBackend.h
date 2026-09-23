#pragma once
#include "AuroraCodecInterfaces.h"
#include <functional>
#include <utility>

namespace aurora::media {

class FunctionKhepriBackend final : public IKhepriBackend {
public:
    using Transform = std::function<Bytes(ByteView)>;

    FunctionKhepriBackend(Transform encoder, Transform decoder)
        : encoder_(std::move(encoder)), decoder_(std::move(decoder)) {
        if(!encoder_ || !decoder_)
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "KHEPRI backend requires encode and decode functions");
    }

    Bytes encode(ByteView input) override {
        try {
            return encoder_(input);
        } catch(const AuroraMediaError&) {
            throw;
        } catch(const std::exception& e) {
            throw AuroraMediaError(ErrorCode::EncodeFailure,
                                   std::string("KHEPRI encode failure: ")+e.what());
        }
    }

    Bytes decode(ByteView input) override {
        try {
            return decoder_(input);
        } catch(const AuroraMediaError&) {
            throw;
        } catch(const std::exception& e) {
            throw AuroraMediaError(ErrorCode::DecodeFailure,
                                   std::string("KHEPRI decode failure: ")+e.what());
        }
    }

private:
    Transform encoder_;
    Transform decoder_;
};

} // namespace aurora::media
