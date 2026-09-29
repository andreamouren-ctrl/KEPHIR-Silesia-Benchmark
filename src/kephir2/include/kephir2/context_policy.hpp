#pragma once

#include "kephir2/backend.hpp"

#include <cstddef>

namespace kephir2 {

struct ContextPolicyDecision {
    std::size_t parent_bytes{512u * 1024u};
    std::size_t inner_chunk_bytes{512u * 1024u};
    std::size_t sampled_bytes{0};
    double quarter_entropy_spread{0.0};
    double window_entropy_std{0.0};
};

// EXP-113 research candidate.
//
// Measures a bounded, content-only stability signal over the logical
// ByteSource. It does not inspect file names/extensions and works equally for
// regular files and SMART/FLAT packed group streams.
//
// EXP-116 candidate policy:
//   spread < 0.10 and local entropy std < 0.12 -> 8 MiB
//   spread < 0.10 and local entropy std >= 0.12 -> 512 KiB
//   spread < 0.20 -> 4 MiB
//   otherwise     -> 512 KiB
//
// At most 256 KiB are sampled through 32 bounded sequential reads.
[[nodiscard]] ContextPolicyDecision choose_adaptive_context(
    const ByteSource& input);

} // namespace kephir2
