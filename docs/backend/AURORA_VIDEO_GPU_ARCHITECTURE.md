# AURORA Video GPU Architecture

Date: 2026-09-23
Status: v0.1 implementation started

## Principle

AURORA Video is GPU-first for high-resolution encode/decode.

The CPU implementation remains:
- bit-exact reference/oracle;
- compatibility fallback;
- test baseline.

## Backend split

GPU:
- motion estimation;
- motion compensation;
- predictor evaluation;
- residual generation;
- residual mapping;
- block/tile analysis;
- reconstruction;
- future transform/quantization tools.

CPU:
- AUM/AUS1 framing;
- timestamps;
- CRC;
- recovery policy;
- network/storage I/O;
- KHEPRI orchestration initially.

KHEPRI remains in-process CPU for the current milestone. GPU acceleration of KHEPRI is a separate research question and will only be attempted when profiling justifies it.

## API

`IVideoMotionCompute` abstracts the motion backend.

Initial implementations:
- CPU Reference
- D3D12 Compute

The first GPU equivalence gate is MC8R4 motion-map identity:
`GPU motion_map == CPU motion_map`

## Windows compute strategy

Primary cross-vendor Windows backend:
- Direct3D 12 Compute + HLSL

This avoids making CUDA a mandatory dependency and supports AMD, NVIDIA and Intel adapters.

CUDA or vendor-specific paths may be added later as optional specialized backends.

## GPU residency rule

Frames/reference frames should remain resident in VRAM across:
- motion estimation;
- compensation;
- residual generation;
- mapping;
- reconstruction.

Avoid round-tripping full 4K frames through system RAM between GPU stages.

Only compact metadata / compressed payload should cross back to CPU when possible.

## Validation strategy

CI can use Microsoft WARP to validate deterministic shader correctness even when no physical GPU is exposed.

Hardware benchmarks must be run separately on real AMD/NVIDIA/Intel GPUs.

## Next GPU milestones

1. D3D12 MC8R4 motion-map equivalence.
2. GPU residual generation.
3. GPU reconstruction.
4. persistent frame/reference textures in VRAM.
5. asynchronous command queues and double/triple buffering.
6. native 4K30 benchmark on hardware.
7. native 4K60 benchmark on hardware.
