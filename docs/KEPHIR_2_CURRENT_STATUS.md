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

## 10. Current validated facts

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

## 11. Current product architecture priority

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

## 12. Validation matrix still required

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

## 13. Current engineering rules

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

## 14. Immediate next milestone

**EXP-80 — Global Router Validation Matrix**

Goal:

Stress the native Analyzer + EXP-79 routing principle across diverse directory shapes before declaring AUTO routing production-stable.

Initial matrix:

- many tiny source/config files;
- homogeneous large files;
- mixed text/binary directory;
- incompressible/high-entropy data;
- zero-rich structured data;
- redundant backup-like data;
- repository workload;
- canonical Silesia.

Acceptance criteria:

- exact lossless roundtrip for every full-layout oracle run;
- selected layout recorded against oracle;
- aggregate and per-dataset selection regret;
- bounded routing overhead;
- no hidden extension-based routing;
- regression report against EXP-77;
- CI PASS.

---

## 15. Current checkpoint summary

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
            ├── EXP-77 ................. SUPERSEDED
            ├── EXP-78 ................. REJECTED AS FINAL ROUTER
            ├── EXP-79 ................. PROMOTED PRINCIPLE
            ├── Routing regret ......... 0 B on current 2-workload matrix
            └── Next ................... EXP-80 validation matrix
```

---

## 16. Update policy

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
