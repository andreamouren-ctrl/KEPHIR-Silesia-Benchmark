# KS-06 — Residual Morphology Controls

Date: 2026-09-23  
GitHub Actions run: 35814008493  
Result: **PASS technically / NO PROMOTION**

Real-audio source: same 52 s Sintel-derived stereo s16le 48 kHz PCM used by KS-03/04/05.

| Variant | Final bytes | % PCM | vs FULL256 |
|---|---:|---:|---:|
| KMRL1 FULL256 ZigZag | **5,552,112** | **55.610%** | baseline |
| RSM packed sign | 5,611,426 | 56.204% | +1.068% |
| RSM FULL256 sign | 5,874,921 | 58.843% | +5.814% |
| RSM transition sign | 5,596,401 | 56.054% | +0.798% |
| FLAC -5 block 960 | 4,730,170 | 47.378% | -14.804% |

All variants reconstructed bit-exactly.

## Decision

No residual sign/magnitude morphology tested in KS-06 beats the KMRL1 FULL256 ZigZag baseline.

These transforms remain background/control techniques and are not promoted into candidate IP. The audio research baseline remains **KMRL1 FULL256**.

The next parallel checkpoint moves to real lossless video, where the same KHEPRI backend will first be measured with background spatial/temporal predictors before any proprietary video mechanism is proposed.
