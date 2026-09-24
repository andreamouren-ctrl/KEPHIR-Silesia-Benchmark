#include "AuroraMediaContainer.h"
#include "AuroraMediaTiming.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

struct Rate { std::uint32_t num,den; const char* name; };

int main() {
    try {
        constexpr std::uint32_t ts=1'000'000;
        constexpr std::uint32_t sample_rate=48'000;
        constexpr std::uint64_t duration_s=600;
        constexpr std::uint64_t audio_packet_samples=960;
        const std::vector<Rate> rates{
            {24000,1001,"23.976"},
            {24,1,"24"},
            {25,1,"25"},
            {30000,1001,"29.97"},
            {30,1,"30"},
            {50,1,"50"},
            {60000,1001,"59.94"},
            {60,1,"60"}
        };

        std::uint64_t worst_clock_error_ticks=0;
        double worst_av_alignment_ms=0.0;

        for(const auto& r:rates) {
            (void)r.name;
            const std::uint64_t frames=
                (duration_s*static_cast<std::uint64_t>(r.num))/r.den;

            std::uint64_t prev=0;
            for(std::uint64_t n=0;n<=frames;++n) {
                const auto pts=video_pts(n,r.num,r.den,ts);
                if(n && pts<prev) throw std::runtime_error("non-monotonic video PTS");
                prev=pts;

                const long double exact=
                    static_cast<long double>(n)*ts*r.den/r.num;
                const auto err=static_cast<std::uint64_t>(
                    std::llround(std::fabs(static_cast<long double>(pts)-exact)));
                worst_clock_error_ticks=std::max(worst_clock_error_ticks,err);
            }

            for(int k=0;k<=100;++k) {
                const std::uint64_t n=(frames*static_cast<std::uint64_t>(k))/100;
                const auto vpts=video_pts(n,r.num,r.den,ts);
                const long double samples_exact=
                    static_cast<long double>(vpts)*sample_rate/ts;
                const auto packet_index=static_cast<std::uint64_t>(
                    std::llround(samples_exact/audio_packet_samples));
                const auto apts=audio_pts(packet_index*audio_packet_samples,
                                          sample_rate,ts);
                const auto delta_ticks = vpts>apts ? vpts-apts : apts-vpts;
                worst_av_alignment_ms=std::max(
                    worst_av_alignment_ms,
                    static_cast<double>(delta_ticks)*1000.0/ts);
            }

            const auto vend=video_pts(frames,r.num,r.den,ts);
            const long double exact_end=
                static_cast<long double>(frames)*ts*r.den/r.num;
            if(std::fabs(static_cast<long double>(vend)-exact_end)>0.500001L)
                throw std::runtime_error("video clock accumulated drift");
        }

        const std::uint64_t samples=duration_s*sample_rate;
        const auto audio_end=audio_pts(samples,sample_rate,ts);
        if(audio_end!=duration_s*ts)
            throw std::runtime_error("audio clock drift");

        if(worst_clock_error_ticks>1)
            throw std::runtime_error("rational timestamp error exceeds one tick");
        if(worst_av_alignment_ms>10.001)
            throw std::runtime_error("A/V packet alignment exceeds half 20ms audio packet");

        std::cout<<"AV_SYNC_PASS duration_s="<<duration_s
                 <<" rates="<<rates.size()
                 <<" timescale="<<ts
                 <<" worst_clock_error_us="<<worst_clock_error_ticks
                 <<" worst_av_packet_alignment_ms="<<worst_av_alignment_ms
                 <<" audio_end_pts="<<audio_end
                 <<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
