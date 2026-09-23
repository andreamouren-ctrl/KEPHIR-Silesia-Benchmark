# AURORA Media Backend v0.4 — Native KHEPRI Video Path

Date: 2026-09-23

## Milestone

AURORA now has a real in-process EXP-37A backend path.

The new adapter directly invokes the generated EXP-37A parser/encode/decode primitives from the same C++ process.

No temporary input/output files are needed for the adapter API.
No subprocess is needed.

Interface:
- ByteView -> KHEPRI memory frame
- KHEPRI memory frame -> Bytes

## Native video components now available

- 4K tile planner
- bounded scheduler/backpressure
- MC8R4 motion search
- motion map generation
- Y/U/V residual generation
- MOD8 residual representation
- ZZ_INTER residual representation
- KSV-09C residual-mode predictor
- EXP-37A in-process memory adapter
- lossless reconstruction

## Important format note

The in-process adapter uses a small internal K37M memory-frame wrapper around the EXP-37A encoded block and raw fallback.

This is an internal backend framing format, not the AUM public container format.

AUM/AUS1 remain the media/container/stream layers.

## Validation

Real EXP-37A memory adapter:
- repetitive buffer roundtrip
- pseudo-random buffer roundtrip
- raw fallback
- corruption rejection
- in-process compression check

CI run:
- 35859282433
- PASS

## Next

Validate the complete native chain:
MC8R4 -> residual mode -> EXP-37A memory adapter -> inverse residual -> frame reconstruction.

Then connect tile packets to AUM/AUS1 and run a first native 4K smoke benchmark.
