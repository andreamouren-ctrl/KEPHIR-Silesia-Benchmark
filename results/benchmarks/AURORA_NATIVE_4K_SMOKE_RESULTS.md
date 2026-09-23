# AURORA Native 4K Smoke Benchmark

Date: 2026-09-23
GitHub Actions run: 35870413928
Status: PASS

## Scope

First end-to-end native 4K backend smoke test.

Pipeline:
- 3840x2160 YUV420p synthetic source
- 256x240 tiles
- 135 tiles/frame
- native C++20 MC8R4 motion search
- native motion map and Y/U/V residual generation
- native MOD8 / ZZ_INTER decision
- real KHEPRI EXP-37A in-process memory adapter
- native decode
- lossless frame reconstruction

No Python frontend, temporary files or KHEPRI subprocess are used in the tested hot path.

## Test size

- generated frames: 3
- inter frames processed: 2
- tiles per frame: 135
- total processed tiles: 270

## Correctness

Result:
- **PASS**

All reconstructed 4K frames matched their original generated frames byte-for-byte.

## Performance

Measured wall time:
- **1.00294 s** for 2 processed frames

Overall serial throughput:
- **1.994 fps**
- **501.47 ms/frame**

Encode section:
- 0.884506 s
- **2.261 fps serial**

Decode section:
- 0.068073 s
- **29.380 fps serial**

## Size / payload diagnostic

Raw residual bytes:
- 24,883,200

Motion-map bytes:
- 259,200

KHEPRI payload + motion/mode bytes:
- 514,580

Diagnostic payload ratio:
- **2.06798%** of residual raw bytes

Important:
this extremely low percentage comes from the deliberately synthetic, highly structured smoke source.
It is not representative of real 4K video compression performance and must not be compared directly with HEVC/AV1/FFV1 results on natural media.

## Memory

Estimated active worker scratch:
- **3,342,336 bytes**
- approximately **3.19 MiB**

This is the bounded active worker estimate for the current 8-tile Streaming4K configuration, not total process RSS.

## Main finding

The dominant 4K bottleneck is currently **encode-side MC8R4 motion search**.

Decode is already approximately 29.4 fps in this fully serial smoke test, while encode is only approximately 2.26 fps.

Therefore the immediate performance priorities are:

1. tile-level parallel execution;
2. faster native motion search;
3. avoid redundant reference extraction/copying;
4. SIMD/vectorized SAD evaluation;
5. multi-resolution/coarse-to-fine motion candidate pruning;
6. then re-measure KHEPRI itself.

## 4K readiness interpretation

The backend has now demonstrated:
- true 3840x2160 operation;
- bounded tile memory;
- native C++20 hot path;
- in-process KHEPRI;
- bit-exact reconstruction.

It has **not yet demonstrated realtime 4K30/4K60 encoding**.

Current serial encode is about 13.3x below 30 fps and 26.5x below 60 fps.

This first benchmark converts the remaining task from an architectural unknown into a measurable performance optimization problem.
