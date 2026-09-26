# KSV-20 H3 — Top-3 Hierarchical Dense Refinement

Date: 2026-09-26
GitHub Actions run: 36236999632
Status: PASS / PRODUCTION-DIRECTION CANDIDATE

## Goal

Recover at least 90% of KSV-17 exhaustive dense-integer motion quality while
remaining materially cheaper than evaluating all 81 vectors/block.

H3 search:
1. evaluate all 25 sparse-even MC8R4 candidates;
2. rank them by exact luma SAD and canonical dense tie order;
3. retain the top three sparse candidates;
4. evaluate the union of their unique 3x3 integer neighborhoods;
5. emit the same KSV-17 dense 0..80 motion-map semantics.

## Aggregate results

- sparse baseline: **24,782,482 B**
- H3: **24,300,942 B**
- exhaustive dense: **24,264,464 B**
- H3 improvement vs baseline: **1.9431%**
- exhaustive dense improvement: **2.0903%**
- dense gain recovered by H3: **92.958%**

Research cost:
- H3 / dense research-time ratio: **0.7059**
- mean H3 candidate evaluations: **39.412/block**
- exhaustive dense: up to **81/block**

## Per source

| Source | Baseline | H3 | Dense | Dense gain recovered |
|---|---:|---:|---:|---:|
| container | 3,615,784 | 3,616,721 | 3,616,370 | 0% |
| coastguard | 4,869,065 | 4,796,146 | 4,796,319 | **100.238%** |
| mobile | 6,030,139 | 5,707,436 | 5,681,252 | **92.495%** |
| football | 5,870,396 | 5,838,974 | 5,836,922 | **93.870%** |
| stefan | 4,397,098 | 4,341,665 | 4,333,601 | **87.300%** |

Mean H3 candidate evaluations:
- container: 40.625
- coastguard: 39.568
- mobile: 40.568
- football: 37.206
- stefan: 39.096

All baseline/H3/dense streams decoded bit-exactly and passed SHA verification.

## Decision

**H3 passes the production-direction gate.**

Required gates:
- >=90% dense gain recovered: **PASS (92.958%)**
- <=80% dense research cost: **PASS (70.59%)**
- materially fewer than 81 candidate evaluations: **PASS (~39.4)**
- bit-exact decode: **PASS**

Do not run H4 as the next priority.

The next engineering step is to move H3 from Python R&D into the native C++ AURORA Media core.

## Next step

**KSV-21 — Native H3 Dense Motion Core**

Implement:
- canonical dense 81-vector indexing;
- 25-vector sparse-even coarse stage;
- exact top-3 ranking;
- unique 3x3 dense refinement neighborhoods;
- FLOOR/TRUNC chroma policy support;
- dense motion-map decoder;
- exact C++/Python conformance vectors;
- native 4K timing and worker scaling.

Production promotion requires:
- bit-exact native roundtrip;
- C++ H3 decisions matching Python reference vectors;
- natural-corpus compression within expected H3 tolerance;
- no unbounded memory growth;
- materially lower encode cost than exhaustive dense.
