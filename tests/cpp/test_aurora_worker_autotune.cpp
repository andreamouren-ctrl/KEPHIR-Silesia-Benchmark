#include "AuroraWorkerAutotune.h"
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace aurora::media;

int main() {
    try {
        {
            const auto c=worker_probe_candidates(135,8,16);
            const std::vector<std::uint32_t> expected{1,2,4,8};
            if(c!=expected) throw std::runtime_error("candidate set 8-cap");
        }
        {
            const auto c=worker_probe_candidates(3,8,64);
            const std::vector<std::uint32_t> expected{1,2,3};
            if(c!=expected) throw std::runtime_error("candidate set small job count");
        }
        {
            const std::vector<WorkerProbeResult> p{
                {1,1.0},{2,0.60},{4,0.40},{8,0.405}
            };
            if(select_fastest_worker_count(p)!=4)
                throw std::runtime_error("1% tie preference must keep 4 workers");
        }
        {
            const auto [best, probes]=autotune_worker_count(
                135,8,
                [](std::uint32_t workers) {
                    switch(workers) {
                        case 1: return 1.0;
                        case 2: return 0.58;
                        case 4: return 0.34;
                        case 8: return 0.36;
                        default: return 10.0;
                    }
                },
                16);
            if(best!=4 || probes.size()!=4)
                throw std::runtime_error("autotune selection");
        }

        std::cout<<"AURORA_WORKER_AUTOTUNE_PASS\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
