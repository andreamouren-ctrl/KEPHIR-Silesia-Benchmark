#pragma once
#include "AuroraMediaError.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <thread>
#include <utility>
#include <vector>

namespace aurora::media {

struct WorkerProbeResult {
    std::uint32_t workers{};
    double seconds{};
};

inline std::vector<std::uint32_t> worker_probe_candidates(
        std::size_t job_count,
        std::uint32_t profile_cap,
        std::uint32_t hardware_threads = std::thread::hardware_concurrency()) {
    if(job_count == 0 || profile_cap == 0)
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "worker autotune requires jobs and a positive profile cap");

    if(hardware_threads == 0)
        hardware_threads = 1;

    const auto limit = static_cast<std::uint32_t>(std::min<std::size_t>(
        job_count,
        std::min<std::uint32_t>(profile_cap, hardware_threads)));

    std::vector<std::uint32_t> out;
    for(std::uint32_t n=1; n<limit; n*=2) {
        out.push_back(n);
        if(n > std::numeric_limits<std::uint32_t>::max()/2)
            break;
    }
    if(out.empty() || out.back()!=limit)
        out.push_back(limit);
    return out;
}

inline std::uint32_t select_fastest_worker_count(
        const std::vector<WorkerProbeResult>& probes) {
    if(probes.empty())
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "worker autotune requires at least one probe");

    auto best = probes.front();
    if(best.workers==0 || !(best.seconds>0.0))
        throw AuroraMediaError(ErrorCode::InvalidArgument,
                               "invalid worker probe");

    for(const auto& p:probes) {
        if(p.workers==0 || !(p.seconds>0.0))
            throw AuroraMediaError(ErrorCode::InvalidArgument,
                                   "invalid worker probe");

        // Prefer the faster result. Within 1%, prefer fewer workers to reduce
        // oversubscription, power draw and scheduler pressure.
        const double threshold = best.seconds * 0.99;
        if(p.seconds < threshold ||
           (p.seconds <= best.seconds * 1.01 && p.workers < best.workers)) {
            best = p;
        }
    }
    return best.workers;
}

template<class ProbeFn>
std::pair<std::uint32_t,std::vector<WorkerProbeResult>> autotune_worker_count(
        std::size_t job_count,
        std::uint32_t profile_cap,
        ProbeFn&& probe,
        std::uint32_t hardware_threads = std::thread::hardware_concurrency()) {
    const auto candidates = worker_probe_candidates(
        job_count, profile_cap, hardware_threads);

    std::vector<WorkerProbeResult> results;
    results.reserve(candidates.size());
    for(const auto workers:candidates) {
        const double seconds = probe(workers);
        if(!(seconds>0.0))
            throw AuroraMediaError(ErrorCode::InternalInvariant,
                                   "worker probe returned non-positive time");
        results.push_back(WorkerProbeResult{workers,seconds});
    }
    return {select_fastest_worker_count(results),std::move(results)};
}

} // namespace aurora::media
