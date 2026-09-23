# KS-05 — Backend-aware predictor selection on FULL256

Date: 2026-09-23  
GitHub Actions run: 35830892046  
Result: **PASS / TOPOLOGY-HEURISTIC REJECTED**

Source: same Sintel-derived stereo s16le 48 kHz PCM used by KS-03/KS-04.  
Raw: 9,984,000 bytes, 52 s.  
SHA-256: `146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744`

All candidates reconstructed bit-exactly.

| Predictor selection | Final bytes | % PCM | Delta vs baseline |
|---|---:|---:|---:|
| FULL256 class-cost baseline | 5,552,224 | 55.6112% | baseline |
| FULL256 physical-plane bytes | **5,551,627** | **55.6052%** | **-0.0108%** |
| FULL256 16/256 recurrence heuristic | 5,573,597 | 55.8253% | +0.3849% |

## Decision

- Reject the first 16/256 hit-count heuristic. It increases final EXP-33H size.
- Keep physical-plane byte selection only as a minor implementation refinement; its gain is too small to define a new architecture.
- Keep KMRL FULL256 itself as the promoted geometry from KS-04.

## Interpretation

A simplistic count of equal bytes at offsets 16 and 256 is not a good proxy for EXP-33H's actual coding cost. KHEPRI's backend model is more complex than raw recurrence counts.

The next checkpoint should therefore alter the residual representation itself rather than trying to approximate the backend with a weak selector.

## KS-06 direction

Test topology-preserving suppression of useless FULL256 padding:
- current FULL256 baseline;
- 16-aligned plane tail trimming;
- stronger 16-aligned sparse plane representation.

Only three geometry variants should be tested.
