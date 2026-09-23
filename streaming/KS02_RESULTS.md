# KS-02 — KMRL-0 Synthetic Checkpoint

Date: 2026-09-23  
GitHub Actions run: 35813037523  
Result: **PASS / PROMOTE TO REAL-MEDIA TEST**

## Purpose

Test whether a KHEPRI-specific residual layout aligned to the existing 16/256 distance topology improves the EXP-33H backend relative to the KS-01 sequential varint residual stream.

This is a technical checkpoint, not evidence of patentability.

## Source

Deterministic stereo s16le, 48 kHz, 12 seconds.  
Raw size: 2,304,000 bytes.  
SHA-256: `4f4c8b837c738b943544450783d15b4766d5790f2a3ebb750e0664e58e0f1fdb`.

## Results

| Variant | Block | Frontend bytes | KHEPRI bytes | % of PCM | vs KS-01 |
|---|---:|---:|---:|---:|---:|
| KS-01 varint | 20 ms | 2,168,584 | 1,810,900 | 78.598% | baseline |
| KMRL-0 | 5 ms | 2,318,315 | 1,766,785 | 76.683% | -2.436% |
| KMRL-0 | 20 ms | 2,296,619 | 1,755,804 | 76.207% | -3.042% |
| KMRL-0 | 40 ms | 2,292,785 | **1,752,771** | **76.075%** | **-3.210%** |

All variants reconstructed bit-exactly.

## Interpretation

KMRL-0 is larger than KS-01 before the backend, yet produces a smaller final KHEPRI archive. That is exactly the behavior the residual-geometry hypothesis predicts: the serialization is less compact as a generic byte stream but exposes structure that EXP-33H compresses more effectively.

This is stronger evidence for the coupling hypothesis than a simple frontend-size win would be.

## Decision

Promote KMRL-0 to KS-03 real-media testing.

Do not freeze the current predictor set or residual classes. The promoted research object is the **residual geometry / backend-topology coupling**, not the individual background predictor formulas.

## Next gate

On real audio:
- bit-exact reconstruction;
- compare direct EXP-33H, KS-01+EXP-33H, KMRL-0+EXP-33H;
- compare against FLAC on the exact same PCM;
- use a 20 ms block target for the first streaming comparison.
