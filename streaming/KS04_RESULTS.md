# KS-04 — KMRL Geometry Sweep

Date: 2026-09-23
GitHub Actions run: 35813375518
Result: PASS

Real-audio source: same 52 s Sintel-derived stereo s16le 48 kHz PCM used by KS-03.

| Variant | Frontend bytes | KHEPRI bytes | % PCM | vs KMRL-0 |
|---|---:|---:|---:|---:|
| KMRL-0 reset + packed fields | 6,932,013 | 5,775,317 | 57.846% | baseline |
| KMRL-1 carry + packed fields | 6,915,377 | 5,757,954 | 57.672% | -0.301% |
| KMRL-1 FULL256 | 8,954,489 | **5,552,105** | **55.610%** | **-3.865%** |
| KMRL-1 class + FULL256 | 14,279,289 | 6,478,016 | 64.884% | +12.167% |
| FLAC -5, block 960 | — | 4,730,170 | 47.378% | -18.097% |

All variants were bit-exact.

## Findings

1. Carrying predictor history between 256-frame tiles inside the same 20 ms chunk is valid but only a small gain.
2. Preserving residual byte planes at exactly 256 positions produces a much larger intermediate representation yet a smaller final EXP-33H archive. This supports the backend-topology coupling hypothesis.
3. An explicit redundant 256-byte class plane is harmful and is rejected.
4. Fixed byte-plane transposition is not treated as the invention: prior-art search found earlier residual bit-plane and dictionary-oriented sample/raster reordering techniques.

## Decision

Promote FULL256 as the technical baseline for the next experiment, while narrowing candidate IP to topology-adaptive, backend-specific residual arrangement rather than fixed plane serialization.
