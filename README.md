# AURORA Media / KHEPRI Codec

Research and backend repository for the **AURORA Media** lossless audio/video codec and its **KHEPRI** compression backend.

> This branch is the canonical audio/video research and backend branch. The general-purpose KHEPRI/Silesia research line remains on `main`.

## Current canonical checkpoints

### Media backend
- KHEPRI **EXP-37A Predictive Dual Match**
- deterministic lossless decode
- specialized media frontend avoids redundant general-purpose structural routing

### Audio
- reversible stereo decorrelation
- predictor residuals + ZigZag
- **KMRL FULL256 + TAIL16**
- bit-exact PCM reconstruction

### Video
- YUV420p8 lossless path
- TEMP and MC8R4 reversible prediction controls
- automatic mode routing
- **20-frame routing-horizon baseline**
- bit-exact reconstruction

### Container / streaming
- **AUM v0.1** native container
- **AUS1 v0.1** stream framing
- CRC, timestamps, index, recovery flags and seek
- Python executable reference
- C++20 native container/session/stream backend
- Python ↔ C++ binary interoperability validated

### General KHEPRI research references
- best structural-router ratio checkpoint: **EXP-48 — 29.8205% Silesia**
- promoted speed-research checkpoint: **FAST-D — 64.63 MB/s encode, 181.67 MB/s decode, 30.9388% Silesia**

These general checkpoints are research references and are not automatically the active media backend.

## Repository map

```text
src/cpp/aurora_media/      canonical C++20 backend
src/python/reference/       executable Python reference
research/audio/             KS audio research
research/video/             KSV video research
research/backend/           media/backend integration research
benchmarks/                 reusable benchmark harnesses
results/                    validated measured results
docs/                       canonical engineering knowledge
tests/                      active backend/reference tests
streaming/                  legacy compatibility only
source_parts/               historical KHEPRI reconstruction assets
```

## Read these first

1. `docs/research/AURORA_MEDIA_TECHNICAL_MASTER.md` — complete scientific/technical history.
2. `docs/architecture/CHECKPOINT_REGISTRY.md` — promoted/rejected checkpoints.
3. `docs/architecture/CANONICAL_FILE_MAP.md` — where every artifact belongs.
4. `docs/architecture/REPOSITORY_STRUCTURE.md` — directory architecture.
5. `docs/specs/AURORA_MEDIA_FORMAT_V01.md` — AUM format baseline.
6. `docs/benchmarks/BENCHMARK_METHOD.md` — benchmark rules.
7. `docs/ip/IP_REGISTER.md` — standard techniques vs candidate project-specific research.
8. `docs/roadmap/BACKEND_ROADMAP.md` — forward backend work.

## Development rules

An experiment becomes an active baseline only after:

- deterministic encode/decode;
- bit-exact verification for lossless modes;
- recorded source/corpus;
- measured compressed size;
- measured throughput where meaningful;
- explicit comparison with the previous checkpoint;
- documented promotion decision.

No GUI code belongs in this backend research branch.

No new production/backend files belong in `streaming/`.
