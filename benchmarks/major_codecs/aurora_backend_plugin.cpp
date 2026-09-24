#include "AuroraKhepriExp37MemoryAdapter.h"
#if defined(AURORA_PLUGIN_FASTD)
#include "AuroraKhepriFastDMemoryAdapter.h"
using PluginBackend=aurora::media::AuroraKhepriFastDMemoryAdapter;
#else
using PluginBackend=aurora::media::AuroraKhepriExp37MemoryAdapter;
#endif

extern "C" {

struct AuroraPluginBuffer {
    unsigned char* data;
    std::size_t size;
};

struct PluginState {
    PluginBackend backend;
    aurora::media::Bytes scratch;
};

void* aurora_backend_create() {
    try { return new PluginState(); } catch(...) { return nullptr; }
}

void aurora_backend_destroy(void* p) {
    delete static_cast<PluginState*>(p);
}

AuroraPluginBuffer aurora_backend_encode(void* p,const unsigned char* data,std::size_t size) {
    try {
        auto* s=static_cast<PluginState*>(p);
        aurora::media::ByteView view(data,size);
        s->scratch=s->backend.encode(view);
        return AuroraPluginBuffer{
            s->scratch.empty()?nullptr:s->scratch.data(),
            s->scratch.size()
        };
    } catch(...) { return AuroraPluginBuffer{nullptr,0}; }
}

AuroraPluginBuffer aurora_backend_decode(void* p,const unsigned char* data,std::size_t size) {
    try {
        auto* s=static_cast<PluginState*>(p);
        aurora::media::ByteView view(data,size);
        s->scratch=s->backend.decode(view);
        return AuroraPluginBuffer{
            s->scratch.empty()?nullptr:s->scratch.data(),
            s->scratch.size()
        };
    } catch(...) { return AuroraPluginBuffer{nullptr,0}; }
}

void aurora_backend_free(unsigned char*) {}

}
