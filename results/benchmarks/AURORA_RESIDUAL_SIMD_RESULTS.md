# AURORA Residual SIMD Results

Date: 2026-09-26
Microbenchmark run: 36219419153
Full-pipeline run: 36219468195
Status: PASS / PROMOTION CANDIDATE

## Change

The MC8R4 luma residual hot path now uses SSE2 for exact byte-wise arithmetic:

Encoder:
- `_mm_sub_epi8` on each 8-byte luma row.

Decoder:
- `_mm_add_epi8` on each 8-byte luma row.

The codec residual is defined modulo 256, so SSE2 byte wraparound is exactly equivalent to the
historical scalar `(a-b)&0xff` and `(a+r)&0xff` operations.

Chroma 4-byte rows retain the scalar path.

Reference switch:
`AURORA_DISABLE_RESIDUAL_SIMD`

## Correctness

- existing MC8R4 regression test: PASS
- encode/decode output fingerprints: identical
- motion maps: identical
- residual bytes: identical
- full-pipeline packed bytes: identical
- bit-exact reconstruction: PASS

## Isolated motion/residual benchmark

256x240 YUV420p8 tile.

| Scenario | Encode speedup | Decode speedup | Combined speedup |
|---|---:|---:|---:|
| Static | **1.741x** | **2.111x** | **1.899x** |
| Low motion | **1.331x** | **2.080x** | **1.533x** |
| Noise/high activity | **1.276x** | **2.114x** | **1.447x** |

Time reduction:
- static encode: 42.55%
- low-motion encode: 24.86%
- noise encode: 21.62%
- decode: approximately 52% across all scenarios

## Full native pipeline benchmark

Pipeline includes:
- tile extraction;
- adaptive MC8R4;
- residual mapping;
- KHEPRI EXP-37A in-process backend;
- parallel workers;
- native lossless decode/reconstruction.

All A/B payload sizes matched.

### 4K / 4 workers

Scalar residual:
- encode: 0.168135 s / **5.9476 fps**
- decode: 0.0195617 s / **51.1203 fps**
- total: 0.187697 s / **5.32774 fps**
- payload: 256,727 bytes

SSE2 residual:
- encode: 0.165480 s / **6.04301 fps**
- decode: 0.0168816 s / **59.2361 fps**
- total: 0.182362 s / **5.48360 fps**
- payload: **256,727 bytes**

Improvement:
- encode: **1.016x**
- decode: **1.159x**
- total: **1.029x**

## Cross-resolution full-pipeline result

The decode path improved across all measured resolutions/worker counts:
- 1080p: 1.109x to 1.501x decode speedup
- 1440p: 1.125x to 1.233x
- 4K: 1.117x to 1.159x

Small encode variance exists at some worker counts because the full pipeline is dominated by
motion search, KHEPRI and scheduling; the isolated residual stage itself showed a clear gain.

## Decision

**PROMOTE.**

Reasons:
- mathematically exact;
- bitstream/payload stable;
- large isolated residual/reconstruction gain;
- measurable full-pipeline decode improvement;
- positive 4K/4-worker total throughput;
- very small implementation complexity.

## Rejected experiment recorded in the same optimization cycle

Paired-row SSE2 SAD (PR #39 / run 36219312895):
- bitstream equivalence: PASS
- low motion: -11.28%
- noise/high activity: -16.59%
- static: neutral

Decision:
- reject paired-row SAD;
- retain the existing one-row SSE2 SAD implementation.

## Next priority

With decode now above 59 fps in the synthetic native 4K/4-worker benchmark, the remaining
performance problem is increasingly encode-side motion search.

Next exact-speed work should focus on:
1. reducing MC8R4 candidate-evaluation overhead further;
2. avoiding work using mathematically safe lower bounds;
3. hardware-adaptive worker selection;
4. natural-media 4K validation.
