#include "AuroraKhepriExp37MemoryAdapter.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

static Bytes repetitive() {
    Bytes b;
    b.reserve(512*1024);
    for(std::size_t i=0;i<512*1024;++i)
        b.push_back(static_cast<Byte>((i/32)%17));
    return b;
}

static Bytes incompressibleish() {
    Bytes b(128*1024);
    std::uint32_t x=0x12345678u;
    for(auto& v:b) {
        x ^= x<<13; x ^= x>>17; x ^= x<<5;
        v=static_cast<Byte>(x);
    }
    return b;
}

static void roundtrip(AuroraKhepriExp37MemoryAdapter& k,const Bytes& src,const char* name) {
    const auto enc=k.encode(src);
    const auto dec=k.decode(enc);
    if(dec!=src) throw std::runtime_error(std::string(name)+" roundtrip failed");
    std::cout<<name<<" raw="<<src.size()<<" framed="<<enc.size()<<"\n";
}

int main() {
    try {
        AuroraKhepriExp37MemoryAdapter k;
        roundtrip(k,{}, "empty");
        roundtrip(k,repetitive(),"repetitive");
        roundtrip(k,incompressibleish(),"pseudo_random");

        auto src=repetitive();
        auto enc=k.encode(src);
        if(enc.size()>=src.size())
            throw std::runtime_error("repetitive data did not compress in-process");

        bool rejected=false;
        enc[0]^=1;
        try { (void)k.decode(enc); }
        catch(const AuroraMediaError& e) { rejected=e.code()==ErrorCode::CorruptHeader; }
        if(!rejected) throw std::runtime_error("corrupt memory frame accepted");

        std::cout<<"KHEPRI_EXP37_MEMORY_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
