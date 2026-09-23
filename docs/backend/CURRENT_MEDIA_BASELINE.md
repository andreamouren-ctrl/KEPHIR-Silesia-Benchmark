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

Active codec path:
- YUV420p8
- 20-frame routing horizon
- three candidates per window:
  - TEMP
  - MC8R4 MOD8
  - MC8R4 ZZ_INTER
- final-size selection using KHEPRI EXP-37A
- AUM v0.1

KSV-08 research aggregate:
- 9,725,887 bytes before outer AUM packet overhead

Full AUM aggregate:
- 9,729,032 bytes

Previous KSV-05 full-AUM aggregate:
- 9,787,973 bytes

Gain:
- 58,941 bytes
- -0.602%

FFV1 aggregate on same diagnostic corpus:
- 10,357,351 bytes

AURORA full AUM is approximately 6.07% smaller than FFV1 on this limited diagnostic corpus.

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
