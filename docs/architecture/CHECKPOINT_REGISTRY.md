# AURORA Compressor / KHEPRI — Checkpoint Registry

**Canonical branch:** `project/aurora-compressor`  
**Qualified 1.0 engine commit:** `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`  
**Qualification run:** `36151845469`

## Status vocabulary

- **PROMOTED** — reference checkpoint.
- **RETAINED** — valid historical/control checkpoint.
- **REJECTED** — measured and not worth repeating without a new hypothesis.
- **ORACLE** — upper-bound measurement, not production-feasible as-is.
- **DIAGNOSTIC** — measurement checkpoint used to locate a bottleneck.
- **RELEASE BASELINE** — integrated, reversible, qualified product checkpoint.

## Early / structural ratio line

| Checkpoint | Status | Result | Decision |
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
| EXP-48 | PROMOTED HISTORICAL RATIO | 29.820498% | Adaptive Structural Router |
| EXP-49 | REJECTED | niche only | extra surface not justified |
| EXP-50R | REJECTED | 0 B saved on SAO | 28-byte record surface |

## Throughput line

| Checkpoint | Status | Ratio | Encode | Decode |
|---|---|---:|---:|---:|
| FAST-A | RETAINED DIAGNOSTIC | 31.3995% | 42.23 MB/s | 116.43 MB/s |
| FAST-D | PROMOTED HISTORICAL SPEED | 30.9388149% | 64.63 MB/s | 181.67 MB/s |
| FAST-E | REJECTED | 31.5409% | 63.62 MB/s | 143.95 MB/s |
| FAST-G | REJECTED | 30.9388149% | no encode gain | slight decode gain |
| FAST-H | RETAINED EXPERIMENT | 30.9681942% | ~6.8% same-run gain | slight gain |
| FAST-AA | REJECTED | 30.9388149% | -19.29% same-run | unchanged |

## Late adaptive / production research

| Checkpoint | Status | Key measured result | Decision |
|---|---|---|---|
| EXP-56 | ORACLE | 63,002,080 B / 29.7265746% | ratio upper bound, too slow |
| EXP-57 | RETAINED | 63,784,645 B / 30.095816% / 39.59 s | fast heuristic direction |
| EXP-58 | RETAINED | 63,745,538 B / 30.077364% | selective verification |
| EXP-59 | RETAINED EXPERIMENT | ratio improved, ~302 s | token transform too expensive |
| EXP-60 | RETAINED | 63,609,809 B / 30.013322% / 51.42 s | indexed token |
| EXP-62 | RETAINED | 63,454,863 B / 29.940213% / 79.17 s | conservative grain |
| EXP-63 | RETAINED | same bytes / 49.76 s | CPU parallel |
| EXP-64 | RETAINED | same bytes / 44.52 s | thread/config tuning |
| EXP-65 | RETAINED | 63,454,863 B / 33.342 s | work parcels |
| EXP-66 | PROMOTED SCHEDULER | 63,454,863 B / 25.972 s | cost-aware LPT scheduler |
| EXP-67 | REJECTED BROAD PSG | +340 B vs EXP-66 / much slower | poor ROI |
| EXP-68 | REJECTED BROAD PSG | +327 B vs EXP-66 / slower | gate insufficient |
| EXP-69 | RETAINED NICHE | global regression; Mozilla local gain | Word-XOR signal discovered |
| EXP-70 | RETAINED ARCHITECTURE | learner cut repeated probes ~83% | Adaptive Experience Engine validated |
| EXP-71 | RETAINED | multi-action learner | PSG low ROI confirmed |
| EXP-72 | PROMOTED GRAIN | 62,927,914 B / 29.691580% | adaptive grain learning |
| EXP-73 | RETAINED | 62,920,997 B | grain + Word-XOR |
| EXP-74 | RETAINED | same 62,920,997 B / predictive WX | Factory prior concept validated |
| EXP-75 | **PROMOTED ALGORITHM** | **62,920,997 B / ~29.6883%** | lazy fine fingerprint; production algorithm checkpoint |
| EXP-76 | **PROMOTED PACKING** | **104,325 B / 14.4353%** on 722,706 B repo snapshot | Smart Directory Packing architecture |

## KEPHIR 1.0 integrated qualification

**Status: RELEASE BASELINE**

Qualified implementation:
- branch: `release/kephir-1.0-final-candidate`
- commit: `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`
- workflow run: `36151845469`
- result: **SUCCESS**
- roundtrip: **FINAL_SHA_ALL_PASS**
- Factory Knowledge v1: **79 positive states**

### Silesia canonical

| Profile | Bytes | Ratio | Compress | Decompress | SHA |
|---|---:|---:|---:|---:|:---:|
| KEPHIR 1.0 cold | 62,953,321 | 29.704% | 96.050 s | 13.645 s | PASS |
| KEPHIR 1.0 Factory | 62,958,288 | 29.706% | 75.057 s | 13.629 s | PASS |

### Real repository qualification

Dataset: **242 files / 759,128 logical bytes**

| Profile | Bytes | Ratio | Compress | Decompress | SHA |
|---|---:|---:|---:|---:|:---:|
| KEPHIR 1.0 cold | 117,523 | 15.481% | 1.703 s | 0.078 s | PASS |
| KEPHIR 1.0 Factory | 117,523 | 15.481% | 0.705 s | 0.080 s | PASS |

## Promotion rule

A checkpoint is not promoted until it has:
1. deterministic encode/decode;
2. SHA/byte-exact roundtrip;
3. identified corpus;
4. compressed size and ratio;
5. throughput data where relevant;
6. comparison with the active checkpoint;
7. explicit promote/reject decision.

A **release baseline** additionally requires integrated archive creation, extraction, metadata restoration and a successful qualification workflow.
