#pragma once
#include "AuroraCodecInterfaces.h"

namespace aurora::media {

class AuroraKhepriExp37MemoryAdapter final : public IKhepriBackend {
public:
    Bytes encode(ByteView input) override;
    Bytes decode(ByteView input) override;
};

} // namespace aurora::media
