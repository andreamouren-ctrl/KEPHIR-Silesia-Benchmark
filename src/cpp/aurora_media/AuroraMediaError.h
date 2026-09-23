#pragma once
#include <stdexcept>
#include <string>

namespace aurora::media {

enum class ErrorCode {
    InvalidArgument,
    UnsupportedVersion,
    UnsupportedCodec,
    CorruptHeader,
    CorruptIndex,
    CorruptPacket,
    CrcMismatch,
    TruncatedInput,
    ResourceLimit,
    SequenceGap,
    EncodeFailure,
    DecodeFailure,
    IoFailure,
    InternalInvariant
};

class AuroraMediaError final : public std::runtime_error {
public:
    AuroraMediaError(ErrorCode code, std::string message)
        : std::runtime_error(std::move(message)), code_(code) {}

    ErrorCode code() const noexcept { return code_; }

private:
    ErrorCode code_;
};

} // namespace aurora::media
