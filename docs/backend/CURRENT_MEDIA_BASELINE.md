# Current AURORA Media Baseline

Date: 2026-09-23

## Audio production/research baseline

Active codec path:
- PCM s16le stereo 48 kHz
- reversible stereo decorrelation
- KMRL
- FULL256
- TAIL16
- KHEPRI EXP-37A
- fixed 2-second recovery packets
- AUM v0.1

Current full-AUM Sintel result:
- 5,546,958 bytes
- bit-exact

KASH-01 research result:
- 5,541,589 bytes
- -0.0968% vs fixed 2 s
- not yet promoted because decision search requires duplicate candidate encodes

## Video baseline

Active operational codec path:
- YUV420p8
- 20-frame routing horizon
- TEMP candidate
- cached MC8R4 motion/residual field
- cheap MC symbol predictor:
  - mean signed residual magnitude < 2.60 -> ZZ_INTER
  - otherwise -> MOD8
- KHEPRI EXP-37A
- AUM v0.1

Operational router: **KSV-09C**

KSV-09C pre-AUM aggregate:
- 9,727,633 bytes

Full AUM aggregate:
- **9,730,778 bytes**

KSV-08 oracle full-AUM aggregate:
- 9,729,032 bytes

Operational penalty versus oracle:
- 1,746 bytes
- +0.01795%

True wall-clock comparison:
- KSV-08: 62.7543 s
- KSV-09C: 34.8628 s
- speedup: 1.80x
- wall-clock reduction: 44.45%

FFV1 aggregate on the same diagnostic corpus:
- 10,357,351 bytes

KSV-09C full AUM remains approximately **6.05% smaller than FFV1** on this limited three-clip diagnostic corpus.

KSV-08 remains the research oracle for validating future cheap predictors.

This is not a general codec superiority claim.

## Backend

- KHEPRI EXP-37A
- AUM v0.1
- AUS1 stream framing
- C++20 container/session/stream backend
- Python executable reference
- Python <-> C++ binary interoperability
- typed codec interfaces
- resource limits
- corruption matrix
- in-process KHEPRI buffer contract

## Immediate priorities

1. replace brute-force KSV-08 three-way trial with a cheaper mode predictor;
2. derive a cheap KASH reset-benefit estimator;
3. extract real EXP-37A encode/decode into the in-process IKhepriBackend contract;
4. continue motion/residual research for medium/high-motion video.


## 4K streaming readiness

Architecture now includes:
- 3840x2160 tile planning;
- 256x240 default tiles;
- 135 tiles/frame at 4K;
- bounded concurrent tile workers;
- bounded in-flight scheduler/backpressure;
- Streaming4K / Balanced / MaxCompression profiles.

Current status:
- architecture/memory scheduling: validated;
- realtime 4K throughput: not yet validated;
- native hot-path port remains required.

See:
`docs/backend/AURORA_4K_STREAMING_READINESS.md`


## Native 4K hot-path progress

Validated C++20 components:
- 4K tile planner
- bounded tile scheduler/backpressure
- Streaming4K / Balanced / MaxCompression profiles
- MOD8 residual mapping
- ZZ_INTER reversible residual mapping
- KSV-09C mean signed residual predictor
- MC8R4 motion search
- motion map generation
- Y/U/V residual generation
- lossless MC8R4 reconstruction
- synthetic 4K tile residual roundtrip

Latest C++20 backend validation:
- GitHub Actions run 35856003939
- result: PASS
- build quality gate: -Wall -Wextra -Werror

The dominant remaining non-native dependency in the active research path is KHEPRI EXP-37A execution through the CLI/file staging path.

Next backend gate:
- expose actual EXP-37A encode/decode through IKhepriBackend using memory buffers;
- connect native video tile motion/residual output directly to that in-process backend;
- run first native 4K raw YUV420p smoke benchmark.
