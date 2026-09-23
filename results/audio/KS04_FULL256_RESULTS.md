# KS-04 — KMRL geometry checkpoint

Date: 2026-09-23  
GitHub Actions run: 35820156416  
Result: **PASS / FULL256 PROMOTED**

Source: same Sintel-derived stereo s16le 48 kHz PCM used by KS-03.  
Raw: 9,984,000 bytes, 52 s.  
SHA-256: `146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744`

All KMRL variants and FLAC reconstructed bit-exactly.

| Variant | Final bytes | % PCM | Delta vs KMRL-0 |
|---|---:|---:|---:|
| KMRL-0 reset packed | 5,775,317 | 57.846% | baseline |
| KMRL-1 carry packed | 5,757,954 | 57.672% | -0.301% |
| **KMRL-1 FULL256** | **5,552,105** | **55.610%** | **-3.865%** |
| KMRL-1 class + FULL256 | 6,478,016 | 64.884% | +12.167% |
| FLAC -5 block 960 | 4,730,170 | 47.378% | -18.097% vs KMRL-0 |

## Decision

Promote **FULL256** as the next KMRL geometry baseline.

Do not promote CLASS_FULL256. The explicit class plane adds enough overhead / adverse structure to erase the benefit.

FULL256 confirms that a deliberately 256-position plane-oriented residual serialization can improve final EXP-33H output even though the intermediate representation is substantially larger than packed KMRL. That behavior strengthens the backend-coupling hypothesis.

The remaining gap to FLAC is still material, so no superiority claim is made.

## Next checkpoint

KS-05 should keep FULL256 fixed and test only a small number of predictor-selection policies against **final KEPHIR archive cost proxies**, not generic residual byte count alone. The goal is to isolate whether predictor choice can be coupled to the same 16/256 topology that made FULL256 successful.
