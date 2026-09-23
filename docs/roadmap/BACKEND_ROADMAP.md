# Backend Roadmap

## Current baseline

AUM v0.1 + AUS1 + C++20 container/session/stream backend + Python reference.

## B03 — Typed codec interfaces

Create stable C++20 interfaces for:
- IAudioEncoder
- IAudioDecoder
- IVideoEncoder
- IVideoDecoder
- IKhepriBackend
- packet/result/error types

## B04 — In-process KHEPRI

Replace production subprocess/file staging with direct memory-buffer API.

Target:
`span<const byte> -> encoded vector<byte>`

and inverse.

## B05 — Native audio codec

Port:
- stereo reversible transform
- predictor residual path
- KMRL
- FULL256
- TAIL16
- EXP-37A integration

Validate stage-by-stage against Python.

## B06 — Native video codec

Port:
- temporal baseline
- MC8R4 control
- routing
- 20-frame horizon baseline

Then continue proprietary research behind the same interface.

## B07 — Incremental container operation

Support:
- non-seekable output
- live packet emission
- optional rolling index
- end-of-stream finalization

## B08 — Robustness

Add:
- parser limits
- invalid sizes
- integer overflow tests
- truncation matrix
- randomized corruption
- fuzzing
- deterministic failure codes

## B09 — Parallel scheduler

Parallelize independent audio/video packets while preserving deterministic output ordering.

## B10 — Larger validation corpus

Run:
- speech
- music
- transients
- animation
- camera motion
- object motion
- texture-heavy scenes
- dark/noisy footage

Do not optimize only for Akiyo/Foreman/Bus.


## Promoted audio recovery baseline

Validated v0.3 checkpoint: 2,000 ms independent audio recovery packets.
This reduced full-AUM Sintel audio from 5,825,143 bytes at 200 ms to 5,546,958 bytes while preserving bounded recovery. Adaptive KASH remains a future research direction.
