# KEPHIR 2 — Current Development Status

**Canonical status file**  
**Branch:** `development/kephir-2-core`  
**Scope:** general-purpose lossless compression only  
**Status date:** 2026-09-26

This file is the single canonical progress snapshot for KEPHIR 2 product development.

It must be updated after every meaningful development milestone, promoted experiment, rejected direction, architecture change, or benchmark that materially changes the project state.

---

## 1. Product objective

KEPHIR 2 is being developed as a **commercial adaptive lossless compression engine**, not merely as another fixed stream compressor.

The product objective is to provide a defensible reason to choose KEPHIR over established compressors by combining:

- content-first analysis;
- automatic global strategy selection;
- adaptive archive layout;
- adaptive grain selection;
- reversible structural transforms;
- encoder-side learned experience;
- predictive LZ parsing;
- adaptive entropy coding;
- cost-aware parallel execution;
- self-contained portable archives.

Primary product promise:

> Analyze the archive, learn which decisions work for the workload, and automatically choose the compression strategy while keeping archives fully portable and independently decodable.

---

## 2. Stable baseline

The qualified stable release line remains:

`KEPHIR 1.0.0-rc1`

The qualified branch is intentionally left untouched while KEPHIR 2 evolves.

KEPHIR 2 development is isolated on:

`development/kephir-2-core`

---

## 3. Current KEPHIR 2 architecture

Current product direction:

```text
Input File / Directory
        ↓
Content Analyzer
        ↓
Global Strategy Router
        ↓
Directory Layout
FLAT / SMART / future HYBRID
        ↓
Adaptive Grain
        ↓
Structural Transform
        ↓
Cost-aware Scheduler
        ↓
Predictive LZ Parser
        ↓
Adaptive Entropy Coding
        ↓
Self-contained Archive
```

The long-term target is a single native C++ production core with no mandatory Python subprocess orchestration.

---

## 4. Native production core

A new native production-oriented source tree has been created:

```text
src/kephir2/
├── CMakeLists.txt
├── README.md
├── include/kephir2/
│   └── strategy.hpp
├── src/
│   └── strategy.cpp
└── tests/
    └── strategy_smoke.cpp
```

Current implemented native components:

- **Global Strategy Router**
- **Native Content Analyzer v1**
- **Compression Planner v1**

Current native capabilities:

- profiles:
  - AUTO
  - FAST
  - BALANCED
  - MAX
- layouts:
  - FLAT
  - SMART
  - HYBRID reserved for future work
- bounded layout probe contract;
- sampled archive/content features;
- uncertainty-aware routing signals;
- integrity verification requirement;
- extended-probe request path.

Build system:

`CMake + C++20`

Current CI status:

**PASS**

The native KEPHIR 2 core currently compiles and passes:
- strategy smoke tests;
- analyzer smoke tests;
- Python↔C++ analyzer parity validation.

---

## 5. EXP-77 — Adaptive Directory Layout

Status:

**SUPERSEDED**

EXP-77 used a metadata-only rule to select between SMART and FLAT.

Observed failures:

### Repository workload

EXP-77 selected:

`SMART`

Oracle:

`FLAT`

Selection regret observed in the latest KEPHIR 2 evaluation lineage:

`1,703 bytes`

### Silesia

EXP-77 selected:

`FLAT`

Oracle:

`SMART`

Selection regret:

`209,661 bytes`

Conclusion:

Static metadata thresholds are insufficient for production AUTO routing.

---

## 6. EXP-78 — Bounded Representative Layout Probe

Status:

**REJECTED AS FINAL ROUTER**

EXP-78 replaced the static EXP-77 decision with bounded compression probes.

Probe budgets:

- stage 1: up to 2 MiB;
- stage 2: up to 12 MiB.

### Repository

Result:

- selected: FLAT;
- oracle: FLAT;
- regret: 0 bytes.

This fixed the repository failure.

### Silesia

Stage-2 sample:

- SMART: 4,315,483 bytes;
- FLAT: 4,315,307 bytes.

Sample difference:

`176 bytes in favor of FLAT`

But the complete archive result was:

- SMART: 62,958,288 bytes;
- FLAT: 63,167,949 bytes.

Actual full-archive SMART advantage:

`209,661 bytes`

EXP-78 therefore still selected the wrong layout.

Conclusion:

A larger sample alone is not sufficient when the measured alternatives are effectively tied.

---

## 7. EXP-79 — Uncertainty-Aware Content-Diversity Router

Status:

**PROMOTED PRINCIPLE / CURRENT ROUTER CANDIDATE**

EXP-79 adds confidence awareness.

Decision policy:

```text
strong probe margin
    → trust measured winner

near-tie probe
    → inspect content diversity

heterogeneous content
    → prefer SMART

still inconclusive
    → request larger bounded probe
```

Content diversity is derived from KEPHIR's byte-level content classifier rather than file extension.

### Repository result

EXP-77:

- selected SMART;
- oracle FLAT;
- regret: 1,703 bytes.

EXP-79:

- selected FLAT;
- oracle FLAT;
- regret: 0 bytes;
- probe time: ~1.63 s.

### Silesia result

Full archive:

- SMART: 62,958,288 bytes;
- ratio: 29.7059%;
- FLAT: 63,167,949 bytes;
- ratio: 29.8048%.

EXP-77:

- selected FLAT;
- regret: 209,661 bytes.

EXP-79:

- selected SMART;
- oracle SMART;
- regret: 0 bytes;
- probe time: ~2.80 s.

Silesia sampled diversity:

- content groups: 5;
- dominant file fraction: ~33.33%;
- dominant byte fraction: ~33.33%.

Aggregate routing result:

```text
EXP-77 aggregate regret: 211,364 bytes
EXP-79 aggregate regret:       0 bytes
Improvement:              211,364 bytes
```

Lossless verification:

**SHA PASS**

Workflow:

**SUCCESS**

---

## 8. EXP-79 native promotion

The EXP-79 routing principle has already been moved into:

`src/kephir2/src/strategy.cpp`

The native router now understands:

- strong-vs-weak probe margins;
- content-family diversity;
- dominant file-family fraction;
- dominant byte-family fraction;
- bounded secondary probe requests.

Current native CI after promotion:

**PASS**

Important limitation:

EXP-79 is not yet considered universally validated.

It currently has zero regret on the two workloads that exposed the EXP-77 failure, but broader validation is still required.

---

## 9. Native Content Analyzer v1

Status:

**PROMOTED**

The content-first classifier used by KEPHIR 1.0 / EXP-79 has now been reproduced in native C++.

Native files:

```text
src/kephir2/include/kephir2/analyzer.hpp
src/kephir2/src/analyzer.cpp
src/kephir2/tests/analyzer_smoke.cpp
src/kephir2/tests/analyzer_dump.cpp
src/kephir2/tests/analyzer_parity.py
```

The analyzer provides:

- exact file count;
- exact logical byte count;
- average file size;
- median file size;
- small-file fraction;
- bounded byte sampling;
- sampled entropy;
- printable fraction;
- zero fraction;
- content-first file classification;
- content-family count;
- dominant file-family fraction;
- dominant byte-family fraction.

Classifier families preserved from the qualified Python implementation:

```text
empty
tiny-text
tiny-binary
encoded-text
text-code
text-config
text-prose
text-generic
binary-zero
binary-low
binary-mid
binary-high
```

The classifier remains extension-independent.

### Python ↔ C++ parity result

CI run validated:

```text
Files checked:              272
Class mismatches:             0
Metric mismatches:            0
Native smoke tests:        PASS
Strategy smoke tests:      PASS
Parity gate:               PASS
```

All 12 content classes were represented in the parity matrix.

Observed class distribution in the validation run:

```text
binary-high      1
binary-low       1
binary-mid       1
binary-zero      1
empty            1
encoded-text     7
text-code      222
text-config     23
text-generic     2
text-prose      11
tiny-binary      1
tiny-text        1
```

Conclusion:

The native analyzer is semantically compatible with the existing Python classifier on the current validation matrix and is promoted into the KEPHIR 2 production core.

---

## 10. Native Compression Planner v1

Status:

**PROMOTED**

A native integration layer now connects:

```text
Directory
    ↓
ContentAnalyzer
    ↓
ArchiveFeatures
    ↓
GlobalRouter
    ↓
StrategyPlan
```

Native files:

```text
src/kephir2/include/kephir2/planner.hpp
src/kephir2/src/planner.cpp
src/kephir2/tests/planner_smoke.cpp
```

The integration smoke test is **PASS**.

This is the first production-oriented end-to-end decision path in KEPHIR 2 that no longer depends on Python for archive analysis or strategy planning.

---

## 11. EXP-80 — Global Router Validation Matrix

Status:

**PASS AS VALIDATION / ROUTER NOT YET FINAL**

EXP-80 tested the EXP-79 routing principle on 8 workloads:

- repository;
- canonical Silesia;
- many tiny source-like files;
- homogeneous large files;
- mixed content;
- incompressible data;
- zero-rich structured data;
- redundant backup-like data.

All SMART and FLAT full-layout runs passed exact roundtrip verification.

Results:

```text
repository          selected FLAT   oracle FLAT   regret 0 B
silesia             selected SMART  oracle SMART  regret 0 B
many_tiny_source    selected FLAT   oracle FLAT   regret 0 B
homogeneous_large   selected FLAT   oracle FLAT   regret 0 B
mixed_content       selected SMART  oracle FLAT   regret 178 B
incompressible      selected FLAT   oracle FLAT   regret 0 B
zero_rich           selected FLAT   oracle FLAT   regret 0 B
redundant_backup    selected FLAT   oracle FLAT   regret 0 B
```

Aggregate:

```text
Correct selections: 7 / 8
Selection accuracy: 87.5%
Total regret:       178 bytes
SHA roundtrip:      PASS on all datasets
```

The single failure revealed a specific policy flaw.

For `mixed_content` the stage-1 probe already favored FLAT:

```text
SMART sample: 263,260 B
FLAT sample:  262,924 B
margin:       ~0.1278%
```

but the content-diversity rule overrode the measured result and forced SMART.

For Silesia the stage-1 probe already favored SMART:

```text
SMART sample: 753,646 B
FLAT sample:  754,225 B
margin:       ~0.0768%
```

and content diversity correctly reinforced that direction.

Conclusion:

Content diversity should be a confidence amplifier, not an unconditional layout override.

This finding defines EXP-81.

---

## 12. EXP-81 — Direction-Preserving Uncertainty Router

Status:

**REJECTED**

EXP-81 attempted to stop content diversity from overriding a near-tie FLAT decision at stage 1.

The stage-1 correction worked conceptually, but the same asymmetric SMART override still existed after the stage-2 probe.

Result:

```text
Correct selections: 7 / 8
Selection accuracy: 87.5%
Total regret:       178 bytes
Routing time:       54.11 s aggregate
SHA roundtrip:      PASS on all datasets
```

The same `mixed_content` workload remained wrong:

```text
selected: SMART
oracle:   FLAT
regret:   178 B
```

and routing cost increased materially because the dataset was escalated to stage 2 before being incorrectly flipped back to SMART.

Conclusion:

The diversity signal must never choose SMART by itself.

New invariant:

> Content diversity is a sample-confidence signal, not a layout preference.

If a sufficiently diverse bounded sample is representative, the router should preserve the measured direction, whether that direction is SMART or FLAT.

This defines EXP-82.

---

## 13. EXP-82 — Representative-Sample Direction Router

Status:

**PROMOTED**

EXP-82 removes the asymmetric SMART bias from the uncertainty policy.

Core rule:

> Content diversity determines whether a bounded sample is representative. It does not select the layout.

Policy:

```text
full-input probe
    → preserve measured SMART/FLAT direction

strong stage-1 margin
    → preserve measured direction

near-tie + representative diversity
    → preserve measured direction

near-tie + homogeneous/non-representative sample
    → bounded stage-2 probe

stage 2
    → preserve measured direction
```

Validation matrix result:

```text
repository          selected SMART  oracle SMART  regret 0 B
silesia             selected SMART  oracle SMART  regret 0 B
many_tiny_source    selected FLAT   oracle FLAT   regret 0 B
homogeneous_large   selected FLAT   oracle FLAT   regret 0 B
mixed_content       selected FLAT   oracle FLAT   regret 0 B
incompressible      selected FLAT   oracle FLAT   regret 0 B
zero_rich           selected FLAT   oracle FLAT   regret 0 B
redundant_backup    selected FLAT   oracle FLAT   regret 0 B
```

Aggregate:

```text
Correct selections: 8 / 8
Selection accuracy: 100%
Total regret:       0 bytes
Routing time:       41.96 s aggregate
SHA roundtrip:      PASS on all datasets
```

The policy has been promoted into the native C++ Global Router.

Native strategy smoke tests, planner integration tests and Python↔C++ analyzer parity remain **PASS** after promotion.

Important limitation:

Routing correctness is now strong on the current matrix, but routing overhead is still too high for a commercial AUTO path.

A second reproducibility limitation was identified: the live repository workload changes as the development branch grows. Future comparison matrices must pin that workload to a fixed commit or replace it with a canonical frozen fixture.

---

## 14. EXP-83 — Reduced-Budget Representative Router

Status:

**REJECTED AS FINAL / SPEED DIRECTION VALIDATED**

EXP-83 kept the EXP-82 routing semantics but reduced the bounded compression-probe budgets:

```text
stage 1: 2 MiB  → 512 KiB
stage 2: 12 MiB → 2 MiB
```

Result on the live eight-workload matrix:

```text
Correct selections: 7 / 8
Selection accuracy: 87.5%
Total regret:       2,172 bytes
Routing time:       14.24 s aggregate
SHA roundtrip:      PASS on all datasets
```

Compared with EXP-82:

```text
Routing time: 41.96 s → 14.24 s
Reduction:    ~66.1%
```

The failure was the live repository workload:

```text
selected: FLAT
oracle:   SMART
regret:   2,172 B
reason:   stage1-strong-margin
```

Important interpretation:

The reduced budgets are highly effective on larger workloads, including Silesia, but a small changing repository is too sensitive to partial sampling.

EXP-83 is therefore not promoted as the final policy.

Two production rules follow:

1. Small archives should use either an exact/full-input decision or a value-aware fast path.
2. Homogeneous directories do not need a SMART/FLAT compression probe when every file belongs to the same content class.

---

## 15. Canonical Router Matrix v1

Status:

**ESTABLISHED**

A frozen benchmark dataset definition now exists at:

`research/packaging/router_matrix_v1.py`

The repository workload is pinned to:

`31f7e6099cec307ad934fd9ec8e6760441567ab5`

This prevents future code changes from silently changing the benchmark input.

Canonical matrix:

- pinned KEPHIR repository snapshot;
- canonical Silesia;
- many tiny source-like files;
- homogeneous large files;
- mixed content;
- incompressible data;
- zero-rich structured data;
- redundant backup-like data.

Synthetic datasets are deterministic and use neutral `.dat` names.

Future router comparisons should use this matrix rather than the live development tree.

---

## 16. EXP-84 — Deterministic-Dominance Fast Router

Status:

**PROMOTED CANDIDATE**

EXP-84 combines:

- Canonical Router Matrix v1;
- exact single-content-class FLAT dominance;
- full-input probe for directories <= 1 MiB;
- 512 KiB stage-1 probe for larger heterogeneous directories;
- 2 MiB stage-2 maximum probe;
- EXP-82 representative-sample direction preservation.

Result:

```text
Correct selections: 8 / 8
Selection accuracy: 100%
Total regret:       0 bytes
Routing time:       3.91 s aggregate
SHA roundtrip:      PASS on all datasets
```

Dataset routing times:

```text
repository          1.463 s   FLAT   correct
silesia             0.634 s   SMART  correct
many_tiny_source    1.044 s   FLAT   deterministic dominance
homogeneous_large   0.009 s   FLAT   deterministic dominance
mixed_content       0.717 s   FLAT   correct
incompressible      0.005 s   FLAT   deterministic dominance
zero_rich           0.009 s   FLAT   deterministic dominance
redundant_backup    0.032 s   FLAT   deterministic dominance
```

Improvement versus EXP-82:

```text
EXP-82 routing: 41.96 s
EXP-84 routing:  3.91 s
Speedup:        ~10.7x
Reduction:      ~90.7%
Correctness:    8/8 → 8/8
Regret:         0 B → 0 B
```

The complete EXP-84 probe policy is now promoted into the native C++ Global Router and Compression Planner contract.

Native AUTO decisions can now explicitly return:
- no probe for single-content-class FLAT dominance;
- full-input probe for heterogeneous directories <= 1 MiB;
- 512 KiB initial probe for larger heterogeneous directories;
- 2 MiB maximum extended probe for unresolved cases.

The full native Core Smoke suite remains **PASS** after this promotion.

EXP-84 is the canonical AUTO router policy.

---

## 17. EXP-85 — Adaptive-Budget Fast AUTO

Status:

**VALIDATED ALTERNATIVE / NOT PROMOTED OVER EXP-84**

EXP-85 combined the single-content-group fast path with:

- full-input probe up to 2 MiB;
- 512 KiB stage-1 probe above that threshold;
- 2 MiB bounded stage-2 probe.

Result:

```text
Correct selections: 8 / 8
Selection accuracy: 100%
Total regret:       0 bytes
Routing time:       5.71 s aggregate
SHA roundtrip:      PASS on all datasets
```

EXP-85 confirms the adaptive-budget direction, but EXP-84 remains the preferred canonical candidate because it achieved the same correctness with **3.91 s aggregate routing** on Canonical Router Matrix v1.

Decision:

**EXP-84 retained as the canonical AUTO router policy.**

---

## 18. EXP-86 — Cheap Cross-File Groupability Estimator

Status:

**VALIDATED ON MATRIX v1 / HOLDOUT REQUIRED**

EXP-86 removes SMART/FLAT compression probes from the routing decision.

Cheap structural features:

- number of content families;
- average file size;
- fraction of bytes in families represented by at least two files;
- dominant-family byte fraction.

Current experimental SMART gate:

```text
average file size >= 512 KiB
AND repeatable-family bytes >= 60%
AND dominant family <= 75%
```

Single-content-family directories retain deterministic FLAT dominance.

Result on Canonical Router Matrix v1:

```text
Correct selections: 8 / 8
Selection accuracy: 100%
Total regret:       0 bytes
Routing time:       1.60 s aggregate
SHA roundtrip:      PASS
```

Routing examples:

```text
repository      0.205 s  FLAT
Silesia         0.054 s  SMART
mixed_content   0.014 s  FLAT
```

Comparison:

```text
EXP-82 routing: 41.96 s
EXP-84 routing:  3.91 s
EXP-86 routing:  1.60 s
```

EXP-86 is approximately 2.4x faster than EXP-84 on Matrix v1 while preserving zero regret.

It is **not promoted yet** because the decision thresholds were derived from a small workload set. A new holdout matrix is required before native promotion.

---

## 19. EXP-87 — Groupability Holdout Validation

Status:

**REJECTED AS FINAL ROUTER / RETAINED AS RISK GATE**

EXP-87 froze all EXP-86 thresholds and evaluated them on eight unseen holdout workloads.

Holdout result:

```text
Correct selections: 4 / 8
Selection accuracy: 50%
Total regret:       262 bytes
Routing time:       0.171 s
SHA roundtrip:      PASS
```

Combined Matrix v1 + holdout v2:

```text
Correct selections: 12 / 16
Selection accuracy: 75%
Total regret:       262 bytes
Routing time:       1.776 s
```

All four holdout failures were false SMART selections:

```text
two_large_repeated_classes      SMART → oracle FLAT   regret 49 B
dominant_large_with_minorities  SMART → oracle FLAT   regret 81 B
two_groups_balanced_large       SMART → oracle FLAT   regret 49 B
three_groups_balanced_large     SMART → oracle FLAT   regret 83 B
```

No observed EXP-87 FLAT prediction was wrong on the current 16-workload matrix.

Conclusion:

The cheap estimator is not robust enough to choose SMART directly.

However, it is useful as a low-cost **risk gate**:

- cheap estimator says FLAT → accept FLAT directly;
- cheap estimator says SMART → require EXP-84 bounded compression evidence.

This defines EXP-88.

---

## 20. EXP-88 — Hybrid Groupability Gate

Status:

**PROMOTED**

EXP-88 combines the cheap EXP-86 groupability estimator with EXP-84 measured evidence.

Policy:

```text
single content class
    → FLAT directly

cheap groupability gate says FLAT
    → FLAT directly

cheap groupability gate says SMART candidate
    → require EXP-84 bounded probe
    → preserve measured direction
```

The cheap gate is therefore asymmetric by design:

> It may eliminate a probe for a conservative FLAT decision, but it may never authorize SMART without measured compression evidence.

Validation on Matrix v1 + holdout v2:

```text
Correct selections: 16 / 16
Selection accuracy: 100%
Total regret:       0 bytes
Routing time:       3.707 s aggregate
SHA roundtrip:      PASS on all 16 datasets
```

Breakdown:

```text
Matrix v1:  8/8 correct, 0 B regret, 1.296 s routing
Holdout v2: 8/8 correct, 0 B regret, 2.411 s routing
```

EXP-88 correctly recovered all four false-SMART failures from EXP-87 by requiring the measured EXP-84 probe.

Native promotion:

- `ArchiveFeatures` now includes multi-file content-group count and repeatable-content byte fraction;
- Native Content Analyzer computes the new groupability statistics;
- Native Global Router contains the EXP-88 conservative FLAT gate;
- positive SMART candidates still request the EXP-84 bounded probe;
- regression tests cover false-SMART holdout behavior;
- full Core Smoke and Python↔C++ classifier parity remain **PASS**.

Decision:

**EXP-88 is now the canonical KEPHIR 2 AUTO pre-routing policy.**

EXP-84 remains the measured authority whenever EXP-88 cannot safely finalize FLAT.

---

## 21. EXP-89 — Native Planner Gate Parity & Performance

Status:

**PARITY PASS / PERFORMANCE OPTIMIZATION REQUIRED**

EXP-89 measured the actual native C++ path:

```text
ContentAnalyzer
    → CompressionPlanner
    → GlobalRouter EXP-88 gate
```

on Matrix v1 + holdout v2.

Result:

```text
Initial-action parity: 16 / 16
Feature mismatches:    0
Core Smoke:            PASS
Aggregate native time: 11.818 s
```

Selected native timings:

```text
repository               1.466 s
Silesia                  0.259 s
many_tiny_source         7.558 s
many_medium_four_groups  0.791 s
redundant_backup         0.316 s
```

Conclusion:

The native decision logic is semantically correct, but the current Analyzer I/O implementation is inefficient for many small/medium files.

Root cause:

`analyze_file()` currently performs a seek/read operation for each stride sample. With thousands of small files this produces millions of tiny file operations. Directory aggregate sampling can repeat similar work.

The router itself is not the bottleneck.

This defines EXP-90.

---

## 22. EXP-90 — Buffered Native Analyzer Fast Path

Status:

**PROMOTED**

EXP-90 changes only the Analyzer I/O strategy for bounded small/medium files.

For files up to 1 MiB:

- perform one bounded sequential read;
- derive the exact same Python-compatible stride sample from the buffer;
- avoid thousands of single-byte seek/read operations.

Large files retain sparse sampling to avoid reading arbitrarily large inputs in full.

Dedicated validation:

```text
Action parity:       16 / 16
Feature mismatches:  0
Classifier parity:   PASS
Core Smoke:          PASS
Aggregate native:    0.574 s
```

Comparison with EXP-89 baseline:

```text
EXP-89 native planning: 11.818 s
EXP-90 native planning:  0.574 s
Speedup:                ~20.6x
Reduction:              ~95.1%
```

Key workload improvements:

```text
repository:
  1466 ms → 17 ms

many_tiny_source:
  7558 ms → 71 ms

many_medium_four_groups:
   791 ms → 4.4 ms

mixed_content:
   157 ms → 2.7 ms
```

Silesia remains approximately 0.28 s because its large files intentionally retain sparse sampling.

Conclusion:

The native KEPHIR 2 analysis + AUTO pre-routing decision layer is now both semantically validated and fast enough to stop being the primary product bottleneck.

Decision:

**Freeze Native Analyzer/Planner decision semantics at this checkpoint and move development to the native archive/execution path.**

---

## 23. Current validated facts

At the present checkpoint:

- KEPHIR 1.0 stable release line remains untouched.
- KEPHIR 2 has a separate native C++ core.
- The production boundary has been separated from `research/`.
- Native CMake build works.
- Native strategy smoke tests pass.
- EXP-77 metadata-only routing is superseded.
- EXP-78 pure bounded probing is insufficient on near-tie samples.
- EXP-79 solves both currently known routing failures.
- EXP-79 aggregate regret on the current two-test matrix is zero.
- Lossless SHA verification passes.
- The Global Router principle is now represented in native C++.

---

## 24. Current product architecture priority

The current production path now contains both the native Content Analyzer and the native Global Router:

```text
Directory
    ↓
Native Content Analyzer
    ↓
Native Global Router
    ↓
Strategy Plan
    ↓
Compression Pipeline
```

The next architectural task is to validate this decision layer over a broader workload matrix and then connect the resulting Strategy Plan to a native archive/compression execution path.

---

## 25. Validation matrix still required

Before EXP-79 can be declared the final production Global Router, it must be tested on:

- very large source repositories;
- thousands of tiny files;
- mixed office/project directories;
- highly homogeneous large-file directories;
- structured binary collections;
- logs and text corpora;
- already-compressed data;
- incompressible/random data;
- mixed binary/text trees;
- redundant backup-style workloads.

For every workload, record:

- selected layout;
- oracle layout;
- selection regret bytes;
- routing overhead;
- archive bytes;
- ratio;
- compression speed;
- decompression speed;
- SHA result.

---

## 26. Current engineering rules

Every future milestone must follow:

```text
one focused hypothesis
→ minimal implementation
→ real CI / benchmark
→ measured result
→ promote or reject
→ update this file
```

No technique is considered promoted only because it is theoretically attractive.

No compression improvement is valid without exact roundtrip verification.

Timing comparisons across different runners must be treated cautiously; same-run A/B measurements are preferred.

Research code may remain Python-based when useful for fast experimentation.

Production functionality should progressively migrate into the native KEPHIR 2 C++ core.

---

## 27. Immediate next milestone

**Native Archive Layer v1**

Goal:

Begin replacing Python archive orchestration with stable native C++ production components without changing compression semantics.

First milestone:

- native unsigned-varint codec;
- native prefix-compressed path manifest;
- deterministic file ordering;
- manifest encode/decode roundtrip;
- path-safety validation;
- byte-parity tests against the current Python manifest format where applicable;
- no compression backend changes yet.

Rationale:

The Analyzer/Planner decision layer is now validated and fast. The next largest architectural debt is Python archive orchestration and temporary-file/subprocess handling.

The archive layer will be migrated incrementally before integrating the compression backend as a native library.

---
## 28. Current checkpoint summary

```text
KEPHIR 1.0
    stable / qualified
            │
            └── untouched

KEPHIR 2
    development/kephir-2-core
            │
            ├── Native C++ core ........ PASS
            ├── CMake .................. PASS
            ├── Strategy smoke test .... PASS
            ├── Analyzer smoke test .... PASS
            ├── Analyzer parity ........ 272 files / 0 mismatches
            ├── Native Analyzer v1 ..... PROMOTED
            ├── Native Planner v1 ...... PROMOTED
            ├── EXP-77 ................. SUPERSEDED
            ├── EXP-78 ................. REJECTED AS FINAL ROUTER
            ├── EXP-79 ................. PROMOTED PRINCIPLE
            ├── EXP-80 ................. 7/8 correct, 178 B regret
            ├── EXP-81 ................. REJECTED, 7/8, 54.11 s routing
            ├── EXP-82 ................. PROMOTED, 8/8, 0 B regret
            ├── EXP-82 routing ......... 41.96 s aggregate
            ├── EXP-83 budget-only ..... REJECTED, 7/8, 14.24 s
            ├── EXP-84 ................. CANONICAL AUTO, 8/8, 0 B
            ├── EXP-84 routing ......... 3.91 s aggregate
            ├── EXP-85 ................. 8/8, 0 B, 5.71 s, not selected
            ├── EXP-86 ................. 8/8 v1, overfit
            ├── EXP-87 holdout ......... 4/8, 262 B regret
            ├── EXP-88 ................. PROMOTED, 16/16, 0 B
            ├── EXP-89 native parity ... 16/16, 0 feature mismatches
            ├── EXP-89 native time ..... 11.818 s baseline
            ├── EXP-90 ................. PROMOTED, 0.574 s
            ├── EXP-90 speedup ......... ~20.6x vs EXP-89
            ├── Router Matrix v1 ....... FROZEN
            ├── Router Matrix v2 ....... HOLDOUT ESTABLISHED
            ├── Native EXP-84 policy ... PASS
            ├── Routing SHA ............ PASS
            └── Next ................... Native Archive Layer v1
```

---

## 29. Update policy

This document is mandatory project state.

After every meaningful KEPHIR 2 development step, it must be updated with:

- new component or experiment;
- exact result;
- PASS / FAIL / PROMOTED / REJECTED status;
- regressions found;
- latest architecture state;
- current benchmark checkpoint;
- immediate next milestone.

This file should always answer the question:

> **Where exactly is KEPHIR 2 right now?**
