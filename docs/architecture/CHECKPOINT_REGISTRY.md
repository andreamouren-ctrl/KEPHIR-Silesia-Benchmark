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


## ULTRA line — EXP-51 to EXP-70

| Checkpoint | Status | Ratio | Encode | Decision |
|---|---|---:|---:|---|
| EXP-51 | REJECTED | 29.820498% | — | 0 B gain vs EXP-48 |
| EXP-52 | REJECTED | 29.820498% | — | structural cascades gave 0 B gain |
| EXP-53 | REJECTED GLOBAL / RETAINED EXPERT | 29.8207452% | — | worse globally, useful per chunk |
| EXP-54 | RETAINED SUCCESS | 29.8204036% | — | adaptive PSG gain |
| EXP-55 | RETAINED SUCCESS | 29.8202413% | — | tri-PSG gain |
| EXP-56 | ORACLE | 29.7265746% | ~2046 s | quality oracle, too slow |
| EXP-57 | RETAINED PRACTICAL | 30.0958160% | 39.59 s | first <60 s ULTRA |
| EXP-58 | RETAINED PRACTICAL | 30.0773639% | 44.07 s* | selective BASE verification |
| EXP-59 | REJECTED IMPLEMENTATION | 30.0133223% | 302.33 s | ratio win, tokenizer too slow |
| EXP-60 | PROMOTED HISTORICAL | 30.0133223% | 51.42 s | indexed tokenization |
| EXP-61 | REJECTED | 30.0133223% | 78.32 s | 0 B gain, too slow |
| EXP-62 | QUALITY SUCCESS / RUNTIME REJECT | 29.9402133% | 79.17 s | better grain/context, >60 s |
| EXP-63 | PROMOTED HISTORICAL | 29.9402133% | 49.76 s | 2-worker parallel |
| EXP-64 | PROMOTED HISTORICAL | 29.9402133% | 44.52 s | configurable workers |
| EXP-65 | PROMOTED HISTORICAL | 29.9402133% | 33.34 s | process work parcels, 4 logical CPUs |
| EXP-66 | **PROMOTED ULTRA CURRENT** | **29.9402133%** | **25.97 s** | cost-aware LPT parcel scheduler; exact EXP-65 bytes |
| EXP-67 | RETAINED DIAGNOSTIC | 29.9400529% | 49.68 s | PSG53/55 verification; -340 B vs EXP-66 but too costly |
| EXP-68 | RETAINED SELECTIVE PSG | 29.9400590% | 38.19 s | gate recovers time; -327 B vs EXP-66, not enough to promote |
| EXP-69 | REJECTED / DIAGNOSTIC | 30.1473318% | 57.74 s | Word-XOR entropy router over-selected; +438,964 B vs EXP-66 |
| EXP-70 | RETAINED LEARNING PROTOTYPE | multi-corpus 31.7245%* | 92.01→76.18 s | online learner reduced probes 401→68 while retaining 4 wins / 16,358 B gain |

\* EXP-58 timing shown from the later multi-corpus Silesia run; earlier runner timing differed substantially.

### Current ULTRA checkpoint

```text
EXP-66
compressed = 63,454,863 B
ratio      = 29.9402133%
encode     = 25.97 s
throughput = 8.16 MB/s
SHA        = PASS
runner CPU = 4 logical
```

### Diagnostic / platform checkpoints

| Item | Status | Result |
|---|---|---|
| EXP-60 bottleneck profile | DIAGNOSTIC | 1,019 backend calls; 39.14 s backend; 16.06 s Python tokenization |
| OpenCL CPU+GPU tokenizer prototype | RETAINED PROTOTYPE | build + exact self-test PASS; hosted CI used CPU fallback, no real GPU timing yet |


### EXP-70 multi-corpus note

EXP-70 is not directly comparable to the single-corpus Silesia ratio rows above because it trained and validated on six corpora totaling **329,460,340 B per epoch**.

Measured learning progression:
- epoch 1: 401 probes, 4 wins, 16,358 B gain, 92.01 s;
- epoch 2: 88 probes, 4 wins, 16,358 B gain, 76.79 s;
- epoch 3: 68 probes, 4 wins, 16,358 B gain, 76.18 s;
- SHA PASS for all epochs.

The experiment validates search-cost learning, not yet a new production ratio checkpoint.

* Multi-corpus aggregate ratio: 31.7245186%.
