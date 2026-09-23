#include "AuroraVideoStreamScheduler.h"
#include <iostream>
#include <stdexcept>

using namespace aurora::media;

int main() {
    try {
        auto plan = make_video_tile_plan(3840,2160,256,240,8,8);
        VideoStreamScheduler q(plan,60,270); // at most two 4K frames worth of tile jobs

        if(!q.can_accept_full_frame()) throw std::runtime_error("first frame rejected");
        if(q.enqueue_frame(0)!=135) throw std::runtime_error("frame 0 tile enqueue");
        if(q.enqueue_frame(1)!=135) throw std::runtime_error("frame 1 tile enqueue");
        if(q.pending()!=270) throw std::runtime_error("queue bound mismatch");
        if(q.can_accept_full_frame()) throw std::runtime_error("queue should apply backpressure");
        if(q.enqueue_frame(2)!=0) throw std::runtime_error("backpressure failed");

        std::size_t popped=0; std::size_t recovery=0;
        while(auto job=q.pop()) {
            ++popped;
            if(job->recovery_frame) ++recovery;
        }
        if(popped!=270 || recovery!=135) throw std::runtime_error("job metadata failure");

        const auto bytes_per_job=plan.estimated_peak_bytes_per_tile();
        const auto active_bytes=bytes_per_job*plan.max_concurrent_tiles;
        if(active_bytes>16u*1024u*1024u)
            throw std::runtime_error("active 4K worker memory budget exceeded");

        std::cout<<"VIDEO_4K_SCHEDULER_PASS jobs="<<popped
                 <<" active_worker_bytes="<<active_bytes<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"FAIL: "<<e.what()<<"\n";
        return 1;
    }
}
