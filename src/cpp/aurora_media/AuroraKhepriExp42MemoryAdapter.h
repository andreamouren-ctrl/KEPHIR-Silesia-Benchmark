#pragma once
#include "AuroraCodecInterfaces.h"

namespace aurora::media {

class AuroraKhepriExp42MemoryAdapter final : public IKhepriBackend {
public:
    Bytes encode(ByteView input) override;
    Bytes decode(ByteView input) override;
};

} // namespace aurora::media
