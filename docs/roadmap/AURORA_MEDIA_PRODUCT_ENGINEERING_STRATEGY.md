# AURORA Media Product Engineering Strategy

Date: 2026-09-26
Status: Active engineering direction

## Product thesis

AURORA Media is a native lossless audio/video system designed around a single principle:

> preserve every source sample exactly while reducing storage, decode cost, recovery latency and integration friction at the same time.

The product is not considered successful because it wins one compression benchmark.
It must provide a balanced advantage across compression, speed, resilience, seek/recovery,
streaming, deterministic behavior and deployability.

## Why a company or user should choose AURORA

The intended differentiators are:

1. **One lossless media architecture for file and stream**
   - AUM container for stored media.
   - AUS framing for streaming.
   - shared codec payloads and recovery semantics.

2. **Bit-exact recovery as a product guarantee**
   - no quality modes hidden behind the lossless profile;
   - decode output must match the source exactly;
   - deterministic encoder decisions are preferred where practical.

3. **Recovery-aware compression**
   - recovery horizon is treated as a codec decision, not only container metadata;
   - audio and video may adapt recovery-point density to content and transport needs;
   - target: fast seek/recovery without the severe ratio loss of naive short independent packets.

4. **CPU/GPU adaptive native backend**
   - portable C++20 baseline;
   - architecture-specific CPU paths;
   - D3D12/GPU acceleration where it produces a measured benefit;
   - no Python or subprocess dependency in production hot paths.

5. **Bounded-memory 4K/8K architecture**
   - tile scheduling;
   - bounded in-flight work;
   - hardware-adaptive worker count;
   - explicit streaming, balanced and max-compression profiles.

6. **Measurable engineering gates**
   - every promoted optimization must preserve lossless correctness;
   - compression changes must be measured on natural media;
   - performance changes must be measured A/B on the same workflow;
   - synthetic results are never promoted as general compression claims.

## Promotion rules

An optimization may enter the production path only when all applicable gates pass:

- bit-exact decode;
- deterministic repeatability;
- corruption/limits tests;
- no unexplained payload regression;
- A/B benchmark on identical hardware;
- natural-media validation where compression behavior changes;
- build clean under `-Wall -Wextra -Werror`.

Speed-only optimizations should preserve the existing bitstream whenever possible.

## Video priorities

### V1 — Exact speed
Goal: make the existing codec faster without changing decisions.

Current work:
- exact zero-SAD MC8R4 fast path;
- persistent worker scratch;
- SIMD SAD;
- hardware-native compiler profile.

Next:
- branch-light exact SAD bounds;
- zero-copy/reference-view tile motion search;
- vectorized residual generation;
- worker-count autotuning.

### V2 — Motion efficiency
Goal: reduce medium/high-motion residual entropy without trading away losslessness.

Research:
- hierarchical exact search;
- predictor reuse across neighboring blocks;
- multi-reference candidate cache;
- content-adaptive search radius;
- motion-field entropy coding.

Every approximation must remain a separate profile until natural-media results justify promotion.

### V3 — Production 4K
Required gates:
- 4K30 encode on target desktop hardware;
- 4K60 decode;
- bounded memory under sustained streams;
- no Python/subprocess hot-path dependencies;
- stable long-run encode/decode tests.

## Audio priorities

### A1 — Adaptive Recovery Horizon
Turn the current fixed 2-second recovery baseline into a cheap estimator that chooses
recovery points without duplicate full candidate encodes.

Targets:
- retain near-single-stream compression efficiency;
- preserve bounded seek/recovery;
- bit-exact decode;
- deterministic packet decisions.

### A2 — Predictor/backend integration
- remove avoidable copies;
- persistent backend state inside permitted recovery windows;
- vectorized decorrelation/predictor transforms;
- multi-channel and high-resolution PCM validation.

### A3 — Competitive corpus
Benchmark against:
- FLAC;
- WavPack;
- ALAC;

using multiple music, speech and mixed-content corpora rather than one source.

## Product quality gates

Before calling AURORA Media production-ready:

- fuzz container/parser input;
- malformed/corrupt packet matrix;
- multi-hour stream soak test;
- random seek/recovery validation;
- deterministic encode repeatability;
- cross-build decode compatibility;
- versioned bitstream conformance vectors;
- CPU capability dispatch tests;
- GPU fallback correctness;
- API/ABI stability plan.

## Current engineering checkpoint

The first optimization under this strategy is **Exact Motion Fast Path**.

It exploits the mathematical lower bound of SAD:

- SAD cannot be less than zero;
- once an ordered candidate reaches zero, no later candidate can improve it;
- the historical tie rule keeps the first minimum candidate;
- therefore stopping on the first zero preserves the exact motion decision.

This gives AURORA a preferred optimization pattern:
**prove equivalence first, then measure the speed gain.**
