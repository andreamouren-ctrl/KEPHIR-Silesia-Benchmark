# KS-06 — Topology-preserving FULL256 sparsity

Date: 2026-09-23  
GitHub Actions run: 35831175812  
Result: **PASS / TAIL16 PROMOTED AS MICRO-OPTIMIZATION**

Source: same Sintel-derived stereo s16le 48 kHz PCM used by previous real-audio checkpoints.  
Raw: 9,984,000 bytes, 52 s.  
SHA-256: `146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744`

All variants reconstructed bit-exactly.

| Geometry | Frontend bytes | Final EXP-33H bytes | % PCM | Delta vs FULL256 |
|---|---:|---:|---:|---:|
| FULL256 baseline | 8,954,489 | 5,552,104 | 55.6100% | baseline |
| **FULL256 TAIL16** | **7,869,535** | **5,543,348** | **55.5223%** | **-0.1577%** |
| FULL256 MASK16 | 7,456,965 | 5,544,324 | 55.5321% | -0.1401% |

## Decision

Promote TAIL16 only as the current best serialization refinement.

MASK16 is smaller before KHEPRI but slightly worse after KHEPRI than TAIL16. This again confirms that minimizing frontend bytes is not identical to minimizing final KHEPRI bytes.

## Interpretation

Layout-level gains are now small. Further micro-tuning of padding is unlikely to close the remaining gap to FLAC by itself.

The next major checkpoint should preserve the winning KMRL/FULL256/TAIL16 representation while testing a materially stronger predictive/residual model. Background predictors may be used as controls, but candidate-IP work should focus on how prediction state, residual geometry and KHEPRI backend behavior interact as one codec system.
