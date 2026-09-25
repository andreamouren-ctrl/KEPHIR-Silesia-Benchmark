# AURORA Compressor / KHEPRI — Technical & Scientific Master Document

**Project:** AURORA Compressor  
**Compression engine:** KHEPRI  
**Canonical branch:** `project/aurora-compressor`  
**Repository:** `andreamouren-ctrl/KEPHIR-Silesia-Benchmark`  
**Document role:** canonical technical/scientific reconstruction of the general-purpose compressor research  
**Status:** living engineering document  
**Updated:** 2026-09-24

---

# 1. Purpose

This document is the canonical engineering record for the general-purpose AURORA Compressor / KHEPRI research line.

It exists to prevent loss of technical knowledge across experiments and to separate the general-purpose compressor from AURORA Media.

It records:

- the architecture and experimental method;
- the Silesia benchmark lineage;
- important EXP checkpoints;
- structural-router research;
- the high-speed FAST line;
- positive and negative experiments;
- ratio/speed trade-offs;
- validation rules;
- current promoted checkpoints;
- repository organization;
- future research priorities.

The media codec has its own master document on `project/aurora-media`.

---

# PART I — PRODUCT AND ENGINE IDENTITY

## 2. Product hierarchy

```text
AURORA
├── AURORA Compressor
│   └── KHEPRI general-purpose lossless engine
└── AURORA Media
    ├── Audio
    ├── Video
    ├── AUM container
    └── AUS1 streaming
```

AURORA Compressor is the general-purpose file/archive product.

KHEPRI is the compression-engine research family beneath it.

The general-purpose line optimizes heterogeneous byte streams, files and archives. The media line may reuse a selected KHEPRI backend, but it is a separate product branch with its own frontend and container architecture.

## 3. Canonical branch boundary

General-purpose work:

```text
project/aurora-compressor
```

Media work:

```text
project/aurora-media
```

The branches share history and KHEPRI concepts, but they must not carry duplicate research trees.

---

# PART II — DEVELOPMENT AND VALIDATION RULES

## 4. Lossless requirement

Every promoted compressor checkpoint must satisfy an exact roundtrip:

```text
SHA256(decoded) == SHA256(original)
```

A smaller archive without a verified decoder roundtrip is not a valid result.

## 5. Experimental discipline

Research should follow:

```text
one hypothesis
→ one minimal implementation
→ one CI/benchmark
→ one measured result
→ promote or reject
```

Large uncontrolled sweeps should be avoided when a smaller experiment can answer the question.

## 6. Benchmark discipline

The canonical general-purpose corpus is Silesia.

Canonical raw size used by the established benchmark line:

```text
211,938,580 bytes
```

Every significant checkpoint should record:

- raw bytes;
- compressed bytes;
- ratio;
- encode throughput;
- decode throughput;
- compiler/build configuration;
- thread count;
- SHA result;
- comparison with the previous checkpoint.

Timing numbers from different runners must not be treated as directly interchangeable. Same-run A/B comparisons are preferred for performance decisions.

---

# PART III — CORE KHEPRI ARCHITECTURE

## 7. Core model

The KHEPRI research line combines several classes of mechanisms:

- LZ-style match finding;
- distance-aware parser cost;
- lazy matching;
- predictive literal/residual modeling;
- arithmetic/range coding;
- adaptive content classification;
- encoder-only topology preferences;
- reversible structural transforms;
- chunk routing;
- experimental multidimensional residual fields.

The system evolved from a direct byte-stream compressor into a prediction-aware and structure-aware compressor.

## 8. Chunked architecture

The research architecture uses bounded chunks.

Chunking enables:

- bounded memory;
- parallel encoding/decoding;
- independent analysis;
- local transform decisions;
- future archive-level threading;
- deterministic recovery boundaries.

Structural routing later operates at chunk granularity.

## 9. Arithmetic/range coding

KHEPRI uses an arithmetic/range-coding backend with adaptive symbol models.

The established 32-bit coder design uses a bounded interval and renormalization. Correctness is treated as a binary-format invariant.

## 10. LZ match search

The parser uses hash-linked candidate chains.

Important concepts include:

- four-byte hash anchors;
- bounded chain depth;
- match length comparison;
- distance penalty;
- lazy lookahead;
- early-stop rules;
- predictive candidate evaluation.

Later FAST work showed that parser traversal is the principal compression hot path.

---

# PART IV — EARLY AND MID-LINE EXPERIMENTS

## 11. EXP-22 — reproducible baseline

EXP-22 is the retained reproducible baseline for the documented research sequence.

Silesia ratio:

```text
33.4880%
```

Its importance is historical: later improvements are measured against a stable, decodable baseline.

## 12. EXP-23 — distance penalty recalibration

EXP-23 substantially changed match economics.

Validated ratio:

```text
31.1942%
```

The experiment showed that parser decisions were highly sensitive to how distance cost was estimated.

## 13. EXP-24 — discrete adaptive distance penalties

EXP-24 introduced content-aware distance penalties.

Best retained checkpoint EXP-24B:

```text
31.0083%
```

Discrete content classes worked better than later continuous formulas.

## 14. EXP-25 — continuous adaptive penalty

The continuous distance-penalty formulation regressed.

Decision:

```text
REJECTED
```

Lesson: a smoother mathematical model is not automatically a better coding model.

## 15. EXP-26 — tuned bands

Best retained checkpoint EXP-26C:

- compressed: 65,633,259 bytes;
- ratio: approximately 30.9681%;
- SHA PASS.

This became part of the later construction chain.

## 16. EXP-27 — adaptive lazy matching

EXP-27A:

- compressed: 65,584,515 bytes;
- ratio: approximately 30.9451%;
- SHA PASS.

Adaptive lazy behavior became another important base layer.

## 17. EXP-28 — fragmented token/distance models

Additional specialization fragmented statistics and regressed.

Decision:

```text
REJECTED
```

## 18. EXP-29

EXP-29 produced only limited refinement and was superseded by the predictive-parser line.

---

# PART V — PREDICTION-AWARE PARSING

## 19. EXP-30 — Predictive Opportunity Cost

EXP-30 introduced one of the central KHEPRI ideas.

Instead of judging a match only from match length and distance, the parser estimates the cost of the literal/residual sequence that the match would replace.

Conceptually:

```text
gain =
predicted_literal_cost(position, length)
- encoded_match_cost(length, distance)
```

EXP-30A:

- compressed: 65,393,000 bytes;
- ratio: approximately 30.85469%;
- encode: approximately 30.93 MB/s in validation;
- decode: approximately 124.43 MB/s;
- SHA PASS.

This joined predictive residual difficulty with LZ parsing.

## 20. EXP-31 — Predictive Surprise Gating

EXP-31 classified literal regions by predictive surprise.

EXP-31C:

- compressed: 65,386,865 bytes;
- ratio: approximately 30.8518%;
- SHA PASS.

The size gain was small and speed worsened, so it remains a research checkpoint rather than the primary backend.

## 21. EXP-32 — sparse predictive field

EXP-32 reduced predictor-evaluation density.

EXP-32A:

- compressed: 65,394,019 bytes;
- ratio: approximately 30.8552%;
- encode: approximately 30.18 MB/s;
- decode: approximately 118.48 MB/s;
- SHA PASS.

This demonstrated that much of the prediction signal could be retained with sparse evaluation.

## 22. EXP-33H — distance topology

EXP-33H added encoder-side preference for useful distance neighborhoods, including geometry near:

- 16;
- 256;
- selected multiples and adjacent distances.

Result:

- compressed: 65,385,121 bytes;
- ratio: approximately 30.850976%;
- encode: approximately 26.80 MB/s;
- decode: approximately 124.21 MB/s;
- SHA PASS.

The decoder format did not require topology metadata: topology influenced encoder choice.

---

# PART VI — REJECTED DIRECT MODELING BRANCHES

## 23. EXP-34 — explicit distance transform

Direct distance-symbol transforms regressed.

Decision: REJECTED.

## 24. EXP-35 — distance delta gating

Explicit distance-delta signaling regressed.

Decision: REJECTED.

## 25. EXP-36 — spatial residual experts

A 16-way positional residual expert fragmented the statistical model.

Decision: REJECTED.

These three experiments established an important rule:

> useful structure is often better expressed through encoder decisions than through extra explicit syntax.

---

# PART VII — DIRECT MAX AND BALANCED BACKENDS

## 26. EXP-37A — Predictive Dual Match

EXP-37 added a prediction-aware candidate in addition to the conventional best LZ candidate.

Validated checkpoint:

- raw: 211,938,580 bytes;
- compressed: 65,308,450 bytes;
- ratio: approximately 30.8148%;
- encode: approximately 18.81 MB/s;
- decode: approximately 127.74 MB/s;
- SHA PASS.

Status:

```text
PROMOTED DIRECT/MAX RESEARCH
```

It is also the backend inherited by AURORA Media because media preprocessing already removes much of the structure that a general router would search for.

## 27. EXP-38A — fused candidate collection

EXP-38 collected conventional and predictive candidates in one traversal.

Result:

- compressed: 65,324,447 bytes;
- ratio: approximately 30.8224%;
- encode: approximately 22.01 MB/s;
- decode: approximately 121.56 MB/s;
- SHA PASS.

The ratio was slightly worse than EXP-37A, but traversal cost improved.

## 28. EXP-39A — two-candidate fused parser

EXP-39 retained two prediction-aware candidates during the fused traversal.

Result:

- compressed: 65,321,697 bytes;
- ratio: approximately 30.8211%;
- encode: approximately 22.33 MB/s;
- decode: approximately 124.17 MB/s;
- SHA PASS.

Status:

```text
RETAINED BALANCED RESEARCH
```

---

# PART VIII — STRUCTURAL DIAGNOSTICS AND ROUTING

## 29. EXP-40 — residual difficulty map

EXP-40 changed the research method from blind transform testing to targeted diagnosis.

It analyzed chunk properties including:

- byte entropy;
- residual entropy;
- lag equality;
- printable fraction;
- compression excess over target.

## 30. EXP-41 — lag 16 / 256 oracle

Reversible residual surfaces were tested per chunk.

Approximate selected oracle gain:

```text
342 KB
```

The gain was highly dataset-specific.

## 31. EXP-42 — multi-lag oracle

Lags included:

```text
1, 4, 16, 64, 256, 1024
```

Important findings:

- x-ray strongly favored lag 4;
- mr strongly favored lag 1024;
- selected potential exceeded approximately 1.14 MB.

## 32. EXP-43 — structural reordering oracle

Delta and transpose transforms were combined.

Important observations:

- x-ray: D4 + T4 saved approximately 1.21 MB;
- mr: D1024 + T1024 saved approximately 540 KB;
- tested selected gain approached approximately 1.78 MB.

This confirmed that heterogeneous files can contain hidden field/record geometry.

## 33. EXP-44 — first end-to-end structural router

EXP-44 converted oracle observations into a reversible chunk router.

Candidates included BASE and selected reversible structural representations.

Silesia:

- compressed: 63,581,600 bytes;
- ratio: approximately 30.0000%;
- SHA PASS.

Status:

```text
RETAINED ROUTER
```

## 34. EXP-46 — structural numeric router

Result:

- compressed: 63,439,947 bytes;
- ratio: approximately 29.9332%;
- SHA PASS.

## 35. EXP-47 — adaptive period oracle

Equivalent selected surface:

- compressed: approximately 63,227,225 bytes;
- ratio: approximately 29.8328%.

Status: ORACLE.

## 36. EXP-48 — Adaptive Structural Router

Current best validated general-purpose ratio checkpoint:

- raw: 211,938,580 bytes;
- compressed: 63,201,140 bytes;
- ratio: 29.820498%;
- SHA PASS.

Status:

```text
PROMOTED GENERAL RATIO RESEARCH
```

The important limitation is encoding cost: EXP-48 evaluates multiple complete reversible representations. It is a ratio-research router, not the final fast production selector.

## 37. EXP-49 — bit/nibble surfaces

Additional bit/nibble representations produced niche gains but did not justify integration.

Decision: REJECTED.

## 38. EXP-50R — 28-byte record surface

On SAO the tested record surface saved 0 bytes.

Decision: REJECTED.

---

# PART IX — HIGH-SPEED RESEARCH LINE

## 39. Change of objective

After reaching approximately 29.82% on Silesia, the project temporarily changed priority from maximum ratio to throughput.

Target:

```text
compression   >= 100 MB/s
decompression ~= 180–200 MB/s or higher
```

The goal is to approach this speed without giving back more compression ratio than necessary.

## 40. FAST-A

FAST-A removed or reduced expensive ratio-oriented work.

Result:

- compressed: 66,547,621 bytes;
- ratio: approximately 31.3995%;
- encode: approximately 42.23 MB/s;
- decode: approximately 116.43 MB/s;
- SHA PASS.

Conclusion: reducing search alone was insufficient.

## 41. FAST-D — promoted speed checkpoint

FAST-D bypassed the expensive predictive/residual literal path and used a simpler raw literal model while retaining matching.

Canonical measured checkpoint:

- compressed: 65,571,285 bytes;
- ratio: 30.9388149%;
- encode: approximately 64.63 MB/s;
- decode: approximately 181.67 MB/s;
- SHA PASS.

Compared with EXP-37A:

- ratio difference: approximately +0.124 percentage points;
- size increase: approximately +263 KiB.

Compared with EXP-48:

- ratio difference: approximately +1.118 percentage points;
- size increase: approximately +2.37 MB.

FAST-D is the current promoted speed research baseline.

## 42. FAST-E

Further chain reduction produced:

- ratio: approximately 31.5409%;
- encode: approximately 63.62 MB/s;
- decode: approximately 143.95 MB/s;
- SHA PASS.

Decision:

```text
REJECTED
```

Reducing search work did not improve effective compression throughput.

## 43. FAST-F profiling

A gprof run on `mozilla` identified the actual hot path.

Observed profile:

- `parse(...)`: roughly 65–69% of sampled CPU, depending on run;
- `encode(...)`: roughly 30–35%;
- `EncModel::enc(...)`: major sub-cost inside encoding;
- range-coder renormalization itself was not the dominant flat-profile cost.

Conclusion:

```text
parser first
range coder second
```

## 44. FAST-G — 64-bit match comparison

FAST-G attempted to accelerate match-length comparison with 64-bit blocks.

Same-run comparison:

FAST-D:
- 65,571,285 bytes;
- 30.9388149%;
- 53.692 MB/s encode;
- 158.663 MB/s decode.

FAST-G:
- 65,571,285 bytes;
- 30.9388149%;
- 52.658 MB/s encode;
- 160.526 MB/s decode.

Compression throughput did not improve.

Decision:

```text
REJECTED
```

## 45. FAST-H — adaptive chain depth

FAST-H adjusted chain depth using chunk repetitiveness.

Same-run comparison:

FAST-D:
- 49.289 MB/s encode;
- 157.527 MB/s decode.

FAST-H:
- compressed: 65,633,551 bytes;
- ratio: 30.9681942%;
- 52.631 MB/s encode;
- 160.499 MB/s decode.

It gained roughly 6.8% encoding speed in that same run, but sacrificed some ratio.

Status:

```text
INTERESTING / NOT PROMOTED
```

The speed gain was too small to replace FAST-D as the main checkpoint.

## 46. FAST-AA — persistent parser scratch experiment

A later focused experiment tested persistent per-worker `head/stamp/prev` parser scratch to avoid allocating and clearing the full hash structures for every chunk.

The archive remained byte-identical.

Same-run full Silesia:

FAST-D:
- 65,571,285 bytes;
- 30.9388149%;
- 52.5288 MB/s encode;
- 147.6601 MB/s decode;
- SHA PASS.

FAST-AA:
- 65,571,285 bytes;
- 30.9388149%;
- 42.3942 MB/s encode;
- 147.6690 MB/s decode;
- SHA PASS.

Encode delta:

```text
-19.2934%
```

Decision:

```text
REJECTED
```

The per-access generation-stamp overhead outweighed the initialization savings.

---

# PART X — CURRENT HOT-PATH KNOWLEDGE

## 47. What is already implemented

Inspection of the actual FAST-D parser confirmed that several obvious optimization ideas are already present:

- `vector<Tok>` is pre-reserved;
- hashing uses a 4-byte anchor;
- match comparison already contains 64-bit block comparison;
- match search is bounded;
- early-stop rules already exist.

These should not be reintroduced as “new” optimizations.

## 48. Current parser priority

The next useful speed research should concentrate on operations executed for every candidate traversal, including:

- cache locality of hash/head/prev data;
- candidate-chain memory access;
- branch behavior inside `findbest`;
- avoiding candidate work that cannot beat the current best;
- reducing cost calculations inside the inner loop;
- precomputed cost tables only where their memory traffic is lower than computation;
- hash function cost;
- candidate ordering;
- cheap structural hints that avoid brute-force multi-encoding.

The project should not simply reduce chain depth aggressively, because FAST-E showed that this can worsen both ratio and practical throughput.

---

# PART XI — CURRENT PROFILE DEFINITIONS

## 49. Ratio / Max profile

Purpose:

- maximize compression;
- allow structural routing;
- accept high research-time encode cost.

Reference:

```text
EXP-48
63,201,140 bytes
29.820498%
SHA PASS
```

## 50. Direct / balanced research profile

Purpose:

- retain strong direct compression without expensive structural multi-probe routing.

References:

```text
EXP-37A — strongest direct Max checkpoint
EXP-39A — balanced fused research checkpoint
```

## 51. Fast profile

Purpose:

- real-time/high-throughput compressor development.

Reference:

```text
FAST-D
65,571,285 bytes
30.9388149%
~64.63 MB/s encode
~181.67 MB/s decode
SHA PASS
```

No profile automatically replaces another.

---

# PART XII — REPOSITORY ORGANIZATION

## 52. Canonical tree

```text
/
├── README.md
├── engine/
│   └── source_parts/
├── research/
│   ├── experiments/
│   ├── validation/
│   ├── oracles/
│   ├── routers/
│   ├── diagnostics/
│   ├── generators/
│   │   ├── general/
│   │   └── speed/
│   └── speed/
├── benchmarks/
│   ├── silesia/
│   └── competitors/
├── docs/
│   ├── architecture/
│   └── research/
└── .github/workflows/
```

## 53. Directory roles

`engine/source_parts/`
: encoded source fragments used to reconstruct the historical KHEPRI C++ baseline.

`research/experiments/`
: chronological EXP sweeps.

`research/validation/`
: validation of named retained/promoted checkpoints.

`research/oracles/`
: upper-bound or selection oracles that are not directly production-feasible.

`research/routers/`
: reversible structural routing experiments.

`research/diagnostics/`
: analysis/profiling tools.

`research/generators/general/`
: source generators for the EXP line.

`research/generators/speed/`
: source generators for FAST/SPEED research.

`research/speed/`
: throughput experiments and same-run A/B harnesses.

`benchmarks/silesia/`
: canonical Silesia benchmark infrastructure.

`benchmarks/competitors/`
: comparisons with external compressors.

## 54. Media separation

AURORA Media is maintained separately on:

```text
project/aurora-media
```

General-purpose research must not be copied into the media working tree.

The media branch carries only the minimal KHEPRI backend construction kit it actually requires.

---

# PART XIII — CHECKPOINT REGISTRY

## 55. General ratio checkpoints

| Checkpoint | Status | Silesia ratio | Main decision |
|---|---|---:|---|
| EXP-22 | RETAINED | 33.4880% | reproducible baseline |
| EXP-23 | RETAINED | 31.1942% | distance penalty recalibration |
| EXP-24B | RETAINED | 31.0083% | discrete adaptive DPEN |
| EXP-25 | REJECTED | regression | continuous DPEN inferior |
| EXP-26C | RETAINED | 30.9681% | tuned bands |
| EXP-27A | RETAINED | 30.9451% | adaptive lazy |
| EXP-28 | REJECTED | regression | fragmented statistics |
| EXP-30A | RETAINED | 30.8547% | Predictive Opportunity Cost |
| EXP-31C | RETAINED | 30.8518% | surprise gating |
| EXP-32A | RETAINED | 30.8552% | sparse predictive field |
| EXP-33H | RETAINED | 30.8510% | distance topology |
| EXP-34 | REJECTED | regression | explicit distance transform |
| EXP-35 | REJECTED | regression | distance delta gate |
| EXP-36 | REJECTED | regression | spatial model fragmentation |
| EXP-37A | PROMOTED DIRECT/MAX | 30.8148% | Predictive Dual Match |
| EXP-38A | RETAINED | 30.8224% | fused traversal |
| EXP-39A | RETAINED BALANCED | 30.8211% | two-candidate fused parser |
| EXP-40 | DIAGNOSTIC | — | residual difficulty map |
| EXP-41 | ORACLE | — | lag16/256 surface |
| EXP-42 | ORACLE | — | multi-lag surface |
| EXP-43 | ORACLE | — | structural reorder |
| EXP-44 | RETAINED ROUTER | 30.0000% | end-to-end structural router |
| EXP-46 | RETAINED | 29.9332% | numeric structural router |
| EXP-47 | ORACLE | 29.8328% equivalent | adaptive period surface |
| EXP-48 | PROMOTED RATIO | 29.8205% | Adaptive Structural Router |
| EXP-49 | REJECTED | niche only | extra surface not justified |
| EXP-50R | REJECTED | no gain | 28-byte record surface |

## 56. Speed checkpoints

| Checkpoint | Status | Ratio | Encode | Decode |
|---|---|---:|---:|---:|
| FAST-A | RETAINED DIAGNOSTIC | 31.3995% | 42.23 MB/s | 116.43 MB/s |
| FAST-D | PROMOTED SPEED | 30.9388% | 64.63 MB/s | 181.67 MB/s |
| FAST-E | REJECTED | 31.5409% | 63.62 MB/s | 143.95 MB/s |
| FAST-G | REJECTED | 30.9388% | no encode gain | slight decode gain |
| FAST-H | RETAINED EXPERIMENT | 30.9682% | ~6.8% same-run gain | slight gain |
| FAST-AA | REJECTED | 30.9388% | -19.29% same-run | unchanged |

---

# PART XIV — CURRENT ENGINEERING PRIORITIES

## 57. Immediate objective

Current performance objective:

```text
FAST-D → 75–80 MB/s encode first
then → 100 MB/s class
decode target → maintain ~180–200 MB/s or better
ratio loss budget → ideally <= 0.1–0.2 percentage points
```

## 58. Recommended experiment order

Do not create several variants at once.

Preferred sequence:

1. profile the exact parser revision;
2. isolate one inner-loop cost;
3. make one minimal patch;
4. run same-run FAST-D A/B;
5. require SHA PASS;
6. record compressed bytes and ratio;
7. promote or reject;
8. only then begin the next hypothesis.

## 59. Structural-router future

EXP-48 proves that structural selection has significant compression value.

The production research problem is not whether routing helps. It is how to predict the useful representation cheaply without fully encoding every candidate.

Future work should investigate low-cost selectors based on measured chunk features rather than brute-force complete candidate compression.

---

# PART XV — FINAL CURRENT STATE

## 60. Canonical current checkpoints

Best general-purpose ratio:

```text
EXP-48 Adaptive Structural Router
raw:        211,938,580 B
compressed: 63,201,140 B
ratio:      29.820498%
SHA:        PASS
```

Best direct Max backend:

```text
EXP-37A Predictive Dual Match
compressed: 65,308,450 B
ratio:      30.8148%
encode:     ~18.81 MB/s
decode:     ~127.74 MB/s
SHA:        PASS
```

Balanced research:

```text
EXP-39A
compressed: 65,321,697 B
ratio:      30.8211%
encode:     ~22.33 MB/s
decode:     ~124.17 MB/s
SHA:        PASS
```

Current speed checkpoint:

```text
FAST-D
compressed: 65,571,285 B
ratio:      30.9388149%
encode:     ~64.63 MB/s
decode:     ~181.67 MB/s
SHA:        PASS
```

## 61. Engineering conclusion

The KHEPRI research has established three separate facts:

1. prediction-aware parsing materially improves direct compression;
2. structural routing can push heterogeneous Silesia compression below 30%;
3. most remaining FAST-D encode cost is in the parser hot path rather than in the range coder.

The current development direction is therefore not to discard the later compression research, but to recover throughput by making parser decisions cheaper and eventually replacing brute-force structural routing with an inexpensive selector.

This document should be updated whenever a checkpoint is promoted, rejected, or changes the architectural understanding of KHEPRI.


---

# PART X — ULTRA LINE UPDATE (EXP-51 → EXP-65)

**Update date:** 2026-09-25

This section records the ULTRA research performed after EXP-50. The hard production constraint for this line is:

```text
full Silesia encode time <= 60 s
lossless SHA roundtrip mandatory
ratio target: progress toward ~26%
```

Canonical Silesia raw size remains **211,938,580 B**.

## EXP-51 — rejected

Expanded structural candidates with additional delta/transpose lags.

Result:
- 63,201,140 B
- 29.820498%
- SHA PASS
- 0 B improvement vs EXP-48

Decision: **REJECTED**.

## EXP-52 — rejected

Selected reversible structural cascades.

Result:
- 63,201,140 B
- 29.820498%
- SHA PASS
- 0 B improvement

Decision: **REJECTED**.

## EXP-53 — globally rejected, retained as adaptive expert

Added PSG mode 5 local-surprise gate.

Result:
- 63,201,664 B
- 29.8207452%
- SHA PASS
- +524 B vs EXP-48

Globally worse, but per-chunk behavior was complementary and useful for later routing.

## EXP-54 — adaptive PSG success

Per-chunk choice between EXP-37/PSG3 and EXP-53/PSG5 across structural modes.

Result:
- 63,200,940 B
- 29.8204036%
- SHA PASS
- 200 B improvement vs EXP-48

Decision: **RETAINED SUCCESS**.

## EXP-55 — tri-PSG success

Added transition-aware PSG mode 6 as third backend expert.

Result:
- 63,200,596 B
- 29.8202413%
- SHA PASS
- 344 B better than EXP-54
- 544 B better than EXP-48

Decision: **RETAINED SUCCESS**.

## EXP-56 — quality/oracle checkpoint

Adaptive subchunk routing over 512/256/128 KiB with exhaustive backend/transform search.

Result:
- 63,002,080 B
- 29.7265746%
- ~2046 s encode in competitor benchmark
- SHA PASS

This is a useful quality oracle but is far outside the 60 s production target.

Decision: **ORACLE**.

## EXP-56 competitor benchmark

On Silesia, selected reference compressors measured:

| Compressor | Ratio | Encode time |
|---|---:|---:|
| 7-Zip/LZMA2 mx9 | 23.0061% | 51.06 s |
| XZ -9 | 23.0234% | 88.11 s |
| Brotli q11 | 23.3863% | 419.91 s |
| Zstd -19 | 24.9579% | 83.98 s |
| Bzip2 -9 | 25.7182% | 17.71 s |
| Brotli q9 | 26.5612% | 33.47 s |
| Zstd -9 | 27.9242% | 3.59 s |
| KHEPRI EXP-56 | 29.7266% | 2046.41 s |

The benchmark demonstrated that a ratio near 26% within 60 s is technically plausible, while KHEPRI still required major routing and execution-efficiency work.

## EXP-57 — first practical <60 s router

Single-pass heuristic router with fixed EXP-37 backend and sampled entropy/residual decisions.

Result:
- 63,784,645 B
- 30.0958160%
- 39.59 s
- 5.35 MB/s
- SHA PASS

Decision: **RETAINED PRACTICAL BASELINE**.

## EXP-58 — selective BASE verification

Every non-BASE structural choice gets one BASE verification encode.

Measured checkpoint:
- 63,745,538 B
- 30.0773639%
- 44.07 s in the later multi-corpus Silesia run
- SHA PASS

An earlier runner measured 25.98 s; timings across runners are not directly interchangeable.

Decision: **RETAINED PRACTICAL CHECKPOINT**.

## EXP-58 multi-corpus benchmark

Validated SHA PASS on:
- Silesia
- Canterbury
- Calgary
- Canterbury Large
- Artificial
- enwik8

Key KHEPRI ratios:
- Silesia: 30.0774%
- Canterbury: 22.7581%
- Calgary: 32.5740%
- Canterbury Large: 29.2163%
- Artificial aggregate: 33.4532%
- enwik8: 36.3672%

Interpretation:
- performance generalizes at roughly 4–5 MB/s;
- strongest ratio weaknesses are text/structured data and Artificial;
- selective improvements are preferable to global brute-force expansion.

## EXP-59 — text token transform, ratio success / speed reject

Added reversible selective text tokenization.

Result:
- 63,609,809 B
- 30.0133223%
- 302.33 s
- SHA PASS
- 135,729 B better than EXP-58

The concept improved ratio but the naive tokenizer was too slow.

Decision: **REJECTED IMPLEMENTATION / RETAINED CONCEPT**.

## EXP-60 — indexed text token transform

Indexed token candidates by first byte.

Result:
- 63,609,809 B
- 30.0133223%
- 51.42 s
- 4.12 MB/s
- SHA PASS

Same compressed output as EXP-59, with runtime reduced from ~302 s to ~51 s.

Decision: **PROMOTED PRACTICAL CHECKPOINT** at that stage.

## EXP-61 — low-confidence structural verification

Budgeted secondary structural checks on uncertain 512 KiB chunks.

Result:
- 63,609,809 B
- 30.0133223%
- 78.32 s
- SHA PASS
- 0 B gain

Decision: **REJECTED**.

## EXP-60 bottleneck diagnostic

Instrumentation-only run preserved the exact EXP-60 output and measured:

- total encode: 59.96 s
- backend encode calls: 1,019
- backend time: 39.14 s
- primary backend time: 26.46 s
- text backend time: 9.73 s
- BASE verification time: 2.95 s
- Python tokenization time: 16.06 s
- tokenization calls: 198
- text backend encodes: 164

This showed that the main scalability limits were:
1. repeated backend process launches / temporary-file I/O;
2. Python tokenization in the hot path;
3. work scheduling and insufficient multicore utilization.

## EXP-62 — conservative grain routing

Raised split thresholds to preserve more 512 KiB context and reduce over-fragmentation, especially on Mozilla/Samba/XML-like data.

Result:
- 63,454,863 B
- 29.9402133%
- 79.17 s
- SHA PASS
- 154,946 B better than EXP-60

Per-file improvements included roughly:
- Mozilla: ~84 KB
- Samba: ~47 KB
- XML: ~22.6 KB

Ratio improved, but runtime exceeded 60 s.

Decision: **QUALITY SUCCESS / RUNTIME REJECT**.

## EXP-63 — two-worker CPU parallelism

Preserved exact EXP-62 decisions but processed independent chunks concurrently with two workers.

Result:
- 63,454,863 B
- 29.9402133%
- 49.76 s
- 4.26 MB/s
- SHA PASS

Decision: **PROMOTED PRACTICAL CHECKPOINT**.

## EXP-64 — configurable thread scaling

Made chunk worker count configurable up to 16. GitHub runner exposed 4 logical CPUs while the experiment requested 16 workers.

Result:
- 63,454,863 B
- 29.9402133%
- 44.52 s
- 4.76 MB/s
- SHA PASS
- exact EXP-63 output

Decision: **PROMOTED SCALING CHECKPOINT**.

## EXP-65 — process-based work parcels

Replaced Python thread scheduling with a process-based work-parcel scheduler:
- worker count capped to actual available CPUs;
- ProcessPool removes the Python GIL from tokenization/transforms;
- tasks are grouped into coarse parcels to reduce IPC/scheduler overhead;
- deterministic output order is preserved.

GitHub runner:
- 4 logical CPUs
- requested workers: 16
- workers actually used: 4
- total work parcels: 119

Result:
- **63,454,863 B**
- **29.9402133%**
- **33.34 s**
- **6.36 MB/s**
- decode: 13.94 s / 15.20 MB/s
- SHA PASS
- exact EXP-64 output

Decision: **PROMOTED — current practical ULTRA checkpoint**.

The improvement from EXP-64 to EXP-65 is architectural: the same compressed bytes are produced while encode time drops from 44.52 s to 33.34 s on the same 4-logical-CPU class of runner.

## CPU+GPU prototype

A separate OpenCL prototype was added for CPU+GPU pipelining.

Current design:
- GPU: token-start matching / highly parallel pre-analysis work;
- CPU: deterministic compaction, KHEPRI entropy coding and packaging;
- exact reversible roundtrip required;
- CPU fallback when no GPU is available.

GitHub hosted CI compiled the prototype and passed its self-test, but the runner had no GPU device and therefore reported:

```text
gpu_used=0
device="CPU fallback"
```

No GPU performance claim is considered valid until measured on a real GPU runner.

## Current ULTRA reference

As of 2026-09-25:

```text
EXP-65
Silesia raw:       211,938,580 B
Compressed:         63,454,863 B
Ratio:              29.9402133%
Encode:             33.34 s
Encode throughput:   6.36 MB/s
SHA:                PASS
Runner CPUs:         4 logical
```

The next scalability objective is better work stealing / load balancing and real 8C/16T plus GPU validation while preserving the exact EXP-65 archive result.
