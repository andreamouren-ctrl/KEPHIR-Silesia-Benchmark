# AURORA Media — 4K Streaming Readiness

Date: 2026-09-23

## Target

Support lossless AURORA Video streaming at 3840x2160 with:
- bounded memory;
- deterministic decoding;
- local recovery;
- tile-level parallelism;
- no requirement to buffer an entire long GOP;
- transport-friendly packetization;
- future native C++20 hot path.

## What is already validated

### 1. Bounded 4K tile plan

Default Streaming4K geometry:
- frame: 3840x2160
- tile: 256x240
- tiles/frame: 135
- halo: 8 pixels
- maximum concurrent active tiles: 8

The planner supports edge tiles for non-exact dimensions.

CI validation:
- PASS

### 2. Bounded scheduler / backpressure

The scheduler:
- emits tile jobs per frame;
- carries frame index and recovery-frame state;
- caps in-flight jobs;
- applies backpressure when the queue is full;
- does not require unbounded frame accumulation.

Validated test:
- two 4K frames maximum in the queue;
- 270 tile jobs maximum in the tested configuration;
- active worker scratch budget remains below 16 MiB in the current estimate.

CI validation:
- PASS

### 3. Streaming framing

AUS1 already provides:
- packet sequence;
- incremental parsing;
- CRC;
- recovery/error signaling;
- bounded parser memory.

### 4. Container/session

AUM v0.1 and the C++20 media session already support:
- indexed recovery points;
- packet CRC;
- deterministic seek;
- bounded parser limits.

## Video profiles

### Streaming4K

Priority:
- latency;
- bounded work;
- parallel tile scheduling.

Current policy:
- KSV-09C operational router;
- no AP256 extra trial;
- 256x240 tiles;
- 8 concurrent tiles;
- 20-frame routing horizon;
- 60-frame recovery interval target.

### Balanced

Allows selected extra search while preserving tile scheduling.

### MaxCompression

Enables AP256 high-motion candidate:
- activation threshold: mean signed residual magnitude > 5.5;
- current measured diagnostic gain: -0.0195% on the small research corpus.

This profile prioritizes size over encode cost.

## Compression baseline

Operational KSV-09C:
- full AUM three-clip aggregate: 9,730,778 bytes;
- approximately 6.05% smaller than FFV1 on the current diagnostic corpus;
- 44.45% lower measured router wall time than the KSV-08 oracle;
- +0.01795% size penalty versus KSV-08 oracle.

KSV-11 MaxCompression gating:
- further -1,897 bytes on the diagnostic corpus;
- activates AP256 on only 5 high-motion windows.

## Important limitation

The codec is **not yet validated as realtime 4K**.

The architecture is now 4K-bounded, but the current media hot path still contains:
- Python video frontends;
- NumPy motion search;
- file staging;
- subprocess KHEPRI invocation;
- non-native candidate orchestration.

Therefore current QCIF timings cannot be extrapolated to 4K60.

## Required gates before declaring 4K realtime ready

1. Native C++20 motion/residual implementation.
2. Native in-process KHEPRI encode/decode.
3. Tile encoder/decoder connected to the scheduler.
4. Parallel worker pool.
5. 4K raw YUV420p smoke roundtrip.
6. 4K30 sustained benchmark.
7. 4K60 sustained benchmark.
8. Memory peak measurement.
9. End-to-end latency measurement.
10. Packet-loss/recovery test at tile and frame boundaries.
11. Broader 4K corpus.
12. Quality is still bit-exact for the lossless profile.

## Next implementation order

1. port MC8R4 residual generation to C++20;
2. port MOD8/ZZ_INTER mapping;
3. wire KSV-09C predictor into native tile jobs;
4. expose KHEPRI through the in-process buffer contract;
5. add worker pool;
6. run first 4K lossless smoke test.
