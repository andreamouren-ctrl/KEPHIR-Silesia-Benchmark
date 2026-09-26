# AURORA Canonical Audio Restore

Date: 2026-09-26
GitHub Actions run: 36220062460
Status: PASS / BASELINE WIRING FIX

## Problem

The documented s16 audio baseline was:
- KMRL carry prediction
- FULL256 residual geometry
- TAIL16 plane trimming
- KHEPRI EXP-37A
- AUM v0.1

The production/reference bridge had drifted to the generalized KMRL v2 frontend instead of
the promoted FULL256 + TAIL16 path.

KASH-02 exposed the regression because fixed 2-second recovery packets measured 5,805,360 bytes.

## Fix

- TAIL16 is now an explicit KRL2 layout: layout 4.
- PCM s16 packets use KRL2 FULL256 + TAIL16.
- PCM 24/32-bit keeps the generalized KMRL v2 path pending separate geometry validation.
- Decoder dispatches by frontend magic and supports both frontend families.

## Correctness

Explicit FULL256 + TAIL16 frontend roundtrip:
- frontend bytes: 7,869,535
- SHA/bit-exact: PASS

Complete AUM recovery-horizon benchmark:
- all variants SHA/bit-exact: PASS

## Results

| Recovery horizon | Packets | Final AUM bytes | % raw |
|---|---:|---:|---:|
| 200 ms | 260 | 5,825,154 | 58.3449% |
| 500 ms | 104 | 5,715,715 | 57.2487% |
| 1000 ms | 52 | 5,599,488 | 56.0846% |
| **2000 ms** | **26** | **5,546,982** | **55.5587%** |

Historical 2000 ms reference:
- 5,546,958 bytes

Difference:
- +24 bytes
- approximately +0.00043%

The 24-byte difference is negligible and accompanies the explicit layout identifier replacing
the prior research-time monkey-patched layout representation.

## Decision

**PROMOTE THE WIRING FIX.**

The canonical s16 production/research path is again FULL256 + TAIL16 + EXP-37A.

The failed KASH-02 predictor run on the generalized frontend is invalid for production
promotion and must not be used to judge adaptive-horizon potential.

Next:
- rerun adaptive recovery research on this restored baseline;
- optimize predictor selection for recovered bytes, not class accuracy.
