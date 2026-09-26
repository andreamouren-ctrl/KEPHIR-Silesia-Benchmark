# KSV-18 H1 — Hierarchical Dense Refinement

Date: 2026-09-26
GitHub Actions run: 36235832986
Status: PASS / RESEARCH CHECKPOINT / NO PRODUCTION PROMOTION

## Goal

Recover KSV-17 dense-integer compression quality without evaluating all 81 vectors/block.

H1 search:
1. evaluate existing 25 sparse-even vectors;
2. select the best sparse vector;
3. evaluate its unique 3x3 integer neighborhood;
4. use KSV-17 dense motion-map semantics unchanged.

## Results

Aggregate:
- baseline: **24,782,482 B**
- H1: **24,384,758 B**
- exhaustive dense: **24,264,464 B**
- H1 gain: **1.6049%**
- dense gain: **2.0903%**
- dense gain recovered: **76.778%**

Research cost:
- H1 / dense research-time ratio: **0.5841**
- mean H1 candidate evaluations: **30.912/block**
- exhaustive dense: up to 81/block

Per source:

| Source | H1 delta | Dense delta | Dense gain recovered |
|---|---:|---:|---:|
| container | +0.0623% | +0.0162% | 0% |
| coastguard | -1.4781% | -1.4940% | **98.93%** |
| mobile | -4.2955% | -5.7857% | 74.24% |
| football | -0.3790% | -0.5702% | 66.46% |
| stefan | -1.0629% | -1.4441% | 73.61% |

All baseline/H1/dense streams decoded bit-exactly and passed SHA verification.

## Decision

**Do not promote H1 directly.**

H1 proves that hierarchical refinement is the correct direction:
- candidate evaluations drop from 81 to ~31;
- research cost drops to ~58%;
- compression retains ~77% of dense gain;
- coastguard is essentially solved.

But mobile/football/stefan show that the best exhaustive odd vector is not always adjacent to the single best sparse-even vector.

## Next experiment

**KSV-19 H2 — Top-2 Sparse Refinement**

Evaluate:
- all 25 sparse-even candidates;
- unique 3x3 neighborhoods around the two best sparse candidates.

Target:
- >=90% of KSV-17 dense gain;
- materially below 81 candidate evaluations/block;
- preserve K17D one-byte motion-map and decoder.
