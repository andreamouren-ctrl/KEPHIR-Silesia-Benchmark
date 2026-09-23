# AURORA Media — 4K Streaming Readiness

Date: 2026-09-23

## Current status

AURORA has now completed its first true native 3840x2160 smoke roundtrip.

Validated:
- bounded 4K tile planner;
- bounded scheduler/backpressure;
- native C++20 MC8R4;
- native residual mapping;
- KSV-09C mode decision;
- real EXP-37A in-process memory backend;
- lossless 4K reconstruction.

## First native 4K measurement

GitHub Actions run:
- 35870413928

Pipeline:
3840x2160 YUV420p -> 256x240 tiles -> MC8R4 -> MOD8/ZZ_INTER -> KHEPRI EXP-37A in RAM -> inverse pipeline.

Measured on 2 processed inter frames:
- overall serial throughput: **1.994 fps**
- average: **501.47 ms/frame**
- encode serial throughput: **2.261 fps**
- decode serial throughput: **29.380 fps**
- active worker scratch estimate: **3.19 MiB**
- bit-exact roundtrip: PASS

The synthetic source was deliberately structured, so its 2.068% payload ratio is a smoke-test diagnostic only, not a real-media compression benchmark.

## What this means

Architecture and correctness are now proven at 4K.

Realtime encode is not yet proven.

The dominant measured bottleneck is MC8R4 encode-side search, not decode and not memory.

## Next optimization gates

### Gate 1 — Parallel tile workers
Run independent tiles concurrently using the existing bounded scheduler.

### Gate 2 — Motion search acceleration
Implement:
- candidate pruning;
- coarse-to-fine search;
- SIMD SAD;
- reuse of reference tile buffers;
- reduced allocations/copies.

### Gate 3 — Native packet path
Connect native tile payloads directly into AUM/AUS1 packet output without staging.

### Gate 4 — Real 4K corpus
Use natural 4K YUV clips and measure:
- final AUM bytes;
- encode/decode fps;
- peak RSS;
- latency;
- recovery behavior.

### Gate 5 — 4K30
Target sustained >=30 fps encode and decode.

### Gate 6 — 4K60
Target sustained >=60 fps where hardware allows.

## Profiles

Streaming4K:
- 256x240 tiles
- 8 concurrent tiles
- KSV-09C
- no AP256 extra trial

Balanced:
- reduced concurrency
- selected extra search

MaxCompression:
- high-motion AP256 enabled
- threshold 5.5

## Current conclusion

AURORA is now **4K-capable in architecture and correctness**, but not yet realtime 4K encoder-ready.

The next work should focus almost entirely on encode-side parallelism and motion-search efficiency.
