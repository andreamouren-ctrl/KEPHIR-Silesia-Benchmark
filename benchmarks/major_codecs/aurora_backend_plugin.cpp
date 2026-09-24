#include "AuroraKhepriExp37MemoryAdapter.h"
#if defined(AURORA_PLUGIN_FASTD)
#include "AuroraKhepriFastDMemoryAdapter.h"
using PluginBackend=aurora::media::AuroraKhepriFastDMemoryAdapter;
#else
using PluginBackend=aurora::media::AuroraKhepriExp37MemoryAdapter;
#endif
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" {

struct AuroraPluginBuffer {
    unsigned char* data;
    std::size_t size;
};

void* aurora_backend_create() {
    try { return new PluginBackend(); } catch(...) { return nullptr; }
}

void aurora_backend_destroy(void* p) {
    delete static_cast<PluginBackend*>(p);
}

AuroraPluginBuffer aurora_backend_encode(void* p,const unsigned char* data,std::size_t size) {
    AuroraPluginBuffer out{nullptr,0};
    try {
        auto* b=static_cast<PluginBackend*>(p);
        aurora::media::ByteView view(data,size);
        auto encoded=b->encode(view);
        if(!encoded.empty()) {
            out.data=static_cast<unsigned char*>(std::malloc(encoded.size()));
            if(!out.data) return AuroraPluginBuffer{nullptr,0};
            std::memcpy(out.data,encoded.data(),encoded.size());
        }
        out.size=encoded.size();
        return out;
    } catch(...) { return AuroraPluginBuffer{nullptr,0}; }
}

AuroraPluginBuffer aurora_backend_decode(void* p,const unsigned char* data,std::size_t size) {
    AuroraPluginBuffer out{nullptr,0};
    try {
        auto* b=static_cast<PluginBackend*>(p);
        aurora::media::ByteView view(data,size);
        auto decoded=b->decode(view);
        if(!decoded.empty()) {
            out.data=static_cast<unsigned char*>(std::malloc(decoded.size()));
            if(!out.data) return AuroraPluginBuffer{nullptr,0};
            std::memcpy(out.data,decoded.data(),decoded.size());
        }
        out.size=decoded.size();
        return out;
    } catch(...) { return AuroraPluginBuffer{nullptr,0}; }
}

void aurora_backend_free(unsigned char* p) { std::free(p); }

}
