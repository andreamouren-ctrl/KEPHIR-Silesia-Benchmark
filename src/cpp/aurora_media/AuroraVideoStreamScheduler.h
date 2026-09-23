#pragma once
#include "AuroraVideoTilePlanner.h"
#include <cstdint>
#include <deque>
#include <optional>

namespace aurora::media {

struct VideoTileJob {
    std::uint64_t frame_index{};
    VideoTile tile{};
    bool recovery_frame{};
};

class VideoStreamScheduler {
public:
    VideoStreamScheduler(VideoTilePlan plan,
                         std::uint32_t recovery_interval_frames,
                         std::size_t max_inflight_jobs)
        : plan_(std::move(plan)),
          recovery_interval_frames_(recovery_interval_frames),
          max_inflight_jobs_(max_inflight_jobs) {
        if(recovery_interval_frames_ == 0 || max_inflight_jobs_ == 0)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"invalid scheduler limits");
    }

    std::size_t enqueue_frame(std::uint64_t frame_index) {
        std::size_t pushed = 0;
        const bool recovery = (frame_index % recovery_interval_frames_) == 0;
        for(const auto& tile : plan_.tiles) {
            if(queue_.size() >= max_inflight_jobs_) break;
            queue_.push_back(VideoTileJob{frame_index,tile,recovery});
            ++pushed;
        }
        return pushed;
    }

    bool can_accept_full_frame() const noexcept {
        return queue_.size() + plan_.tiles.size() <= max_inflight_jobs_;
    }

    std::optional<VideoTileJob> pop() {
        if(queue_.empty()) return std::nullopt;
        auto job = queue_.front();
        queue_.pop_front();
        return job;
    }

    std::size_t pending() const noexcept { return queue_.size(); }
    std::size_t capacity() const noexcept { return max_inflight_jobs_; }
    const VideoTilePlan& plan() const noexcept { return plan_; }

private:
    VideoTilePlan plan_;
    std::uint32_t recovery_interval_frames_{};
    std::size_t max_inflight_jobs_{};
    std::deque<VideoTileJob> queue_;
};

} // namespace aurora::media
