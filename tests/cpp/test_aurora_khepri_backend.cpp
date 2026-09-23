#include "AuroraKhepriBackend.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

int main() {
    try {
        FunctionKhepriBackend backend(
            [](ByteView in) {
                Bytes out(in.rbegin(),in.rend());
                out.insert(out.begin(),0xA7);
                return out;
            },
            [](ByteView in) {
                if(in.empty() || in.front()!=0xA7)
                    throw std::runtime_error("bad synthetic KHEPRI frame");
                Bytes out(in.begin()+1,in.end());
                std::reverse(out.begin(),out.end());
                return out;
            }
        );

        const Bytes src{1,2,3,4,5,6};
        const auto enc=backend.encode(src);
        const auto dec=backend.decode(enc);
        if(dec!=src) throw std::runtime_error("buffer backend roundtrip");

        bool typed=false;
        try {
            const Bytes bad{0};
            (void)backend.decode(bad);
        } catch(const AuroraMediaError& e) {
            typed = e.code()==ErrorCode::DecodeFailure;
        }
        if(!typed) throw std::runtime_error("decode failure was not typed");

        std::cout<<"IN_PROCESS_KHEPRI_CONTRACT_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
