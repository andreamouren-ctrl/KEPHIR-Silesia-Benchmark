# KS-01 — PCM reversible frontend result

Date: 2026-09-23  
GitHub Actions run: 35812230160  
Result: **PASS**

## Baseline

Backend: KHEPRI EXP-33H DIST-TOPO-AGGR.

Synthetic deterministic source:
- stereo s16le
- 48 kHz
- 12 seconds
- 2,304,000 raw bytes
- SHA-256: `4f4c8b837c738b943544450783d15b4766d5790f2a3ebb750e0664e58e0f1fdb`

Direct KHEPRI output:
- 2,304,114 bytes
- direct compression expanded this signal slightly

## Results

| Block | Frontend bytes | Frontend + KHEPRI | Delta vs direct KHEPRI | SHA |
|---:|---:|---:|---:|---|
| 5 ms | 2,191,186 | 1,831,956 | -20.492% | PASS |
| 10 ms | 2,176,094 | 1,818,031 | -21.096% | PASS |
| 20 ms | 2,168,584 | 1,810,895 | -21.406% | PASS |
| 40 ms | 2,164,821 | **1,806,969** | **-21.576%** | PASS |

Best result in this sweep: 40 ms.

Relative to raw PCM, the best archive is about 78.43% of the source size. This is not yet competitive evidence versus dedicated audio codecs; it only proves that the reversible media-aware transform exposes structure that EXP-33H was not exploiting directly.

## Timing note

The frontend is currently Python research code. For the 40 ms mode:
- frontend encode: 0.474 s for 12 s audio
- frontend decode: 0.774 s
- KHEPRI encode after frontend: 0.146 s
- KHEPRI decode: 0.045 s

The prototype is already faster than real time despite Python, but C++ timing will be required before any performance claim.

## Decision

**Promote the architecture, not the parameters.**

The first hypothesis is supported:
> a media-aware reversible predictor/decorrelator in front of KHEPRI can materially improve compression compared with feeding raw PCM directly to the generic backend.

The exact delta/varint transform is only a baseline.

## Next experiments

1. KS-02: real PCM music/speech corpus.
2. Add matched-block FLAC comparison.
3. Predictor sweep: fixed delta, LPC orders, adaptive per-block selection.
4. Replace byte-oriented varint residual representation with KHEPRI-native residual classes.
5. Move the winning frontend to C++.
6. Test 5/10/20 ms first for interactive streaming; keep 40 ms as an efficiency reference.
