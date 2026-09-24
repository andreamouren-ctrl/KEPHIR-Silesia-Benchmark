# KHEPRI / AURORA Media — Checkpoint Registry

**Branch:** `project/aurora-media`  
**Purpose:** canonical registry of promoted, retained and rejected checkpoints.

## Status vocabulary

- **PROMOTED** — current reference for a defined profile.
- **RETAINED** — valid and useful historical/control checkpoint.
- **REJECTED** — valid experiment that should not be repeated without a new hypothesis.
- **ORACLE** — measures potential by trying alternatives; not production-feasible as-is.
- **HYPOTHESIS** — documented research direction without promotion.

## General KHEPRI checkpoints

| Checkpoint | Status | Main result | Decision |
|---|---|---:|---|
| EXP-22 | RETAINED | 33.4880% Silesia | reproducible baseline |
| EXP-23 | RETAINED | 31.1942% | distance penalty recalibration |
| EXP-24B | RETAINED | 31.0083% | discrete adaptive DPEN |
| EXP-25 | REJECTED | regression | continuous DPEN inferior |
| EXP-26C | RETAINED | 30.9681% | tuned bands |
| EXP-27A | RETAINED | 30.9451% | adaptive lazy baseline |
| EXP-28 | REJECTED | regression | model fragmentation |
| EXP-30A | RETAINED | 30.8547% | Predictive Opportunity Cost |
| EXP-31C | RETAINED | 30.8518% | surprise gating, slower |
| EXP-32A | RETAINED | 30.8552% | sparse predictive field |
| EXP-33H | RETAINED | 30.8510% | distance topology |
| EXP-34 | REJECTED | regression | direct distance transform overhead |
| EXP-35 | REJECTED | regression | distance delta gate overhead |
| EXP-36 | REJECTED | regression | 16-way spatial expert fragmentation |
| EXP-37A | **PROMOTED MEDIA BACKEND / MAX DIRECT** | 30.8148% | predictive dual match |
| EXP-38A | RETAINED | 30.8224% | fused one-pass candidate collection |
| EXP-39A | RETAINED BALANCED RESEARCH | 30.8211% | two-candidate fused parser |
| EXP-40 | DIAGNOSTIC | — | residual difficulty map |
| EXP-41 | ORACLE | ~342 KB selected gain | lag16/256 surface |
| EXP-42 | ORACLE | ~1.14 MB selected gain | multi-lag surface |
| EXP-43 | ORACLE | ~1.78 MB selected gain | structural reorder |
| EXP-44 | RETAINED ROUTER | 30.0000% | first end-to-end structural router |
| EXP-46 | RETAINED | 29.9332% | structural numeric router |
| EXP-47 | ORACLE | 29.8328% equivalent | adaptive period surface |
| EXP-48 | **PROMOTED GENERAL RATIO RESEARCH** | **29.8205%** | adaptive structural router |
| EXP-49 | REJECTED | niche gain only | bit/nibble surfaces not worth integration |
| EXP-50R | REJECTED | 0 B saved on SAO | 28-byte record surface failed |

## High-speed checkpoints

| Checkpoint | Status | Ratio | Encode | Decode | Notes |
|---|---|---:|---:|---:|---|
| FAST-A | RETAINED DIAGNOSTIC | 31.3995% | 42.23 MB/s | 116.43 MB/s | search reductions insufficient |
| FAST-D | **PROMOTED SPEED RESEARCH** | **30.9388%** | **64.63 MB/s** | **181.67 MB/s** | literal predictor bypass |
| FAST-E | REJECTED | 31.5409% | 63.62 MB/s | 143.95 MB/s | shorter chain did not help |

## Audio checkpoints

| ID | Status | Key decision |
|---|---|---|
| KS-01 | RETAINED | reversible stereo + delta + ZigZag frontend proved useful |
| KS-02 | RETAINED | KMRL residual lattice established |
| KS-03 | RETAINED | real-audio validation |
| KS-04 FULL256 | PROMOTED COMPONENT | fixed 256-position residual planes |
| KS-04 CLASS_FULL256 | REJECTED | explicit class plane regressed |
| KS-05 topology heuristic | REJECTED | weak proxy for backend cost |
| KS-06 TAIL16 | **PROMOTED AUDIO SERIALIZATION** | sparse tail preserving useful geometry |
| KS-06 MASK16 | RETAINED CONTROL | smaller frontend but larger final archive |
| KS-07 EXP-44 media routing | REJECTED FOR DEFAULT MEDIA | all chunks selected BASE; duplicated work |
| KS-07B EXP-37A direct | **PROMOTED AUDIO/VIDEO BACKEND** | smaller than EXP-33H with less routing overhead |

## Video checkpoints

| ID | Status | Key decision |
|---|---|---|
| KSV-01 | RETAINED | baseline lossless video path |
| KSV-02 | RETAINED | multi-clip validation |
| KSV-03 | RETAINED | motion-compensation control |
| KSV-04 fixed lattice | REJECTED | block-major residual reordering regressed |
| KSV-05 adaptive routing | **PROMOTED VIDEO ROUTER** | TEMP/MC8R4 automatic selection |
| 20-frame horizon | **PROMOTED ROUTING HORIZON BASELINE** | best aggregate among 10/20/30/50 |
| KASH | HYPOTHESIS | adaptive state/reset horizon research |

## Container/backend checkpoints

- AUM v0.1 binary container — **PROMOTED BASELINE**.
- AUS1 v0.1 stream framing — **PROMOTED BASELINE**.
- Python reference implementation — **ACTIVE REFERENCE**.
- C++20 container/session/stream implementation — **ACTIVE BACKEND**.
- Python ↔ C++ interoperability — **VALIDATED**.

## Promotion rule

No future experiment becomes a baseline until it has:

1. deterministic encode/decode;
2. bit-exact verification for lossless paths;
3. recorded corpus and configuration;
4. measured size and throughput;
5. explicit comparison against the current checkpoint;
6. a documented promote/reject decision.
