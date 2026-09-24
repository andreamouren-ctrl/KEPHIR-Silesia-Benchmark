# AURORA Compressor / KHEPRI — Checkpoint Registry

**Branch:** `project/aurora-compressor`

## Status vocabulary
- **PROMOTED** — reference checkpoint for a defined profile.
- **RETAINED** — valid historical/control checkpoint.
- **REJECTED** — tested and not worth repeating without a new hypothesis.
- **ORACLE** — useful upper-bound measurement, not directly production-feasible.
- **DIAGNOSTIC** — measurement checkpoint used to locate a bottleneck.

## General-purpose ratio line

| Checkpoint | Status | Ratio / result | Decision |
|---|---|---:|---|
| EXP-22 | RETAINED | 33.4880% | reproducible baseline |
| EXP-23 | RETAINED | 31.1942% | distance penalty recalibration |
| EXP-24B | RETAINED | 31.0083% | discrete adaptive DPEN |
| EXP-25 | REJECTED | regression | continuous DPEN inferior |
| EXP-26C | RETAINED | 30.9681% | tuned bands |
| EXP-27A | RETAINED | 30.9451% | adaptive lazy |
| EXP-28 | REJECTED | regression | model fragmentation |
| EXP-30A | RETAINED | 30.8547% | Predictive Opportunity Cost |
| EXP-31C | RETAINED | 30.8518% | surprise gating |
| EXP-32A | RETAINED | 30.8552% | sparse predictive field |
| EXP-33H | RETAINED | 30.8510% | distance topology |
| EXP-34 | REJECTED | regression | explicit distance transform |
| EXP-35 | REJECTED | regression | distance delta gate |
| EXP-36 | REJECTED | regression | spatial expert fragmentation |
| EXP-37A | PROMOTED DIRECT/MAX | 30.8148% | Predictive Dual Match |
| EXP-38A | RETAINED | 30.8224% | fused candidate collection |
| EXP-39A | RETAINED BALANCED | 30.8211% | two-candidate fused parser |
| EXP-40 | DIAGNOSTIC | — | residual difficulty map |
| EXP-41 | ORACLE | ~342 KB selected gain | lag16/256 surface |
| EXP-42 | ORACLE | ~1.14 MB selected gain | multi-lag surface |
| EXP-43 | ORACLE | ~1.78 MB selected gain | structural reorder |
| EXP-44 | RETAINED ROUTER | 30.0000% | first end-to-end structural router |
| EXP-46 | RETAINED | 29.9332% | structural numeric router |
| EXP-47 | ORACLE | 29.8328% equivalent | adaptive period surface |
| EXP-48 | PROMOTED RATIO | 29.820498% | Adaptive Structural Router |
| EXP-49 | REJECTED | niche only | extra surface not justified |
| EXP-50R | REJECTED | 0 B saved on SAO | 28-byte record surface |

## Speed line

| Checkpoint | Status | Ratio | Encode | Decode | Decision |
|---|---|---:|---:|---:|---|
| FAST-A | RETAINED DIAGNOSTIC | 31.3995% | 42.23 MB/s | 116.43 MB/s | insufficient speed |
| FAST-D | PROMOTED SPEED | 30.9388149% | 64.63 MB/s | 181.67 MB/s | current speed baseline |
| FAST-E | REJECTED | 31.5409% | 63.62 MB/s | 143.95 MB/s | shorter chain regressed |
| FAST-G | REJECTED | 30.9388149% | 52.658 MB/s same-run | 160.526 MB/s | 64-bit compare no encode gain |
| FAST-H | RETAINED EXPERIMENT | 30.9681942% | 52.631 MB/s same-run | 160.499 MB/s | ~6.8% same-run encode gain but ratio loss |
| FAST-AA | REJECTED | 30.9388149% | 42.3942 MB/s same-run | 147.6690 MB/s | persistent scratch -19.29% encode |

## Promotion rule

A checkpoint is not promoted until it has:
1. deterministic encode/decode;
2. SHA/byte-exact roundtrip;
3. identified corpus;
4. compressed size and ratio;
5. throughput data where relevant;
6. comparison with the active checkpoint;
7. explicit promote/reject decision.
