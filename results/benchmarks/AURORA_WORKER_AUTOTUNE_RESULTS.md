# AURORA Worker Autotune Results

Date: 2026-09-26
GitHub Actions run: 36224964385
Status: PASS / PROMOTION CANDIDATE

## Goal

Replace hard-coded worker counts with a measured hardware-adaptive selection.

The autotuner bounds candidates by:
- hardware thread count;
- available job/tile count;
- profile concurrency cap.

It selects the fastest measured candidate and prefers fewer workers when timings are
within approximately 1%, avoiding pointless oversubscription and scheduler pressure.

## Validation

Unit test:
- `AURORA_WORKER_AUTOTUNE_PASS`

Full native pipeline:
- YUV420p8 4K
- KHEPRI EXP-37A in process
- exact motion fast path
- interior motion fast path
- residual SIMD

Runner:
- hardware_concurrency: 4
- Balanced profile cap: 6
- valid probe candidates: 1, 2, 4

4K probe results:

| Workers | Encode | Decode | Total |
|---:|---:|---:|---:|
| 1 | 2.147 fps | 23.637 fps | 1.969 fps |
| 2 | 4.243 fps | 47.766 fps | 3.897 fps |
| 4 | **6.141 fps** | **62.223 fps** | **5.589 fps** |

Selected:
- **4 workers**
- fastest valid candidate: **4 workers**
- selection overhead vs fastest: **0.000%**

A separate manual 8-worker run on the same job reached 5.631 total fps, only about
0.75% above the 4-worker result while oversubscribing the runner's reported four
hardware threads. The autotune policy intentionally excludes that configuration.

Payload:
- unchanged at **256,727 bytes**

## Decision

**PROMOTE worker autotuning infrastructure.**

The production principle is not "use four workers".
The production principle is:
**measure a small bounded candidate set on the actual machine and use the best
non-oversubscribed configuration for that profile/workload.**
