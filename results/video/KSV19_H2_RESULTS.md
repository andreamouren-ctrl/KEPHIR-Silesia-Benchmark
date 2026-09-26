# KSV-19 H2 — Top-2 Hierarchical Dense Refinement

Date: 2026-09-26
GitHub Actions run: 36236356786
Status: PASS / RESEARCH CHECKPOINT / CLOSE TO PROMOTION GATE

## Goal

Improve KSV-18 H1 by refining around the two best sparse-even MC8R4 vectors
instead of only the single best vector.

Search:
1. evaluate all 25 sparse-even candidates;
2. rank them by exact luma SAD and dense tie order;
3. take the best two sparse vectors;
4. evaluate the union of their unique 3x3 integer neighborhoods;
5. emit the same K17D dense motion-map semantics and reuse the existing decoder.

## Results

Aggregate:
- baseline: **24,782,482 B**
- H2: **24,325,419 B**
- exhaustive dense: **24,264,464 B**
- H2 gain: **1.8443%**
- dense gain: **2.0903%**
- dense gain recovered: **88.233%**

Research cost:
- H2 / dense research-time ratio: **0.6526**
- mean H2 candidate evaluations: **35.542/block**
- exhaustive dense: up to 81/block

Per source:

| Source | H2 delta | Dense delta | Dense gain recovered |
|---|---:|---:|---:|
| container | +0.0367% | +0.0162% | 0% |
| coastguard | -1.4952% | -1.4940% | **100.08%** |
| mobile | -5.0384% | -5.7857% | 87.08% |
| football | -0.4864% | -0.5702% | 85.29% |
| stefan | -1.2103% | -1.4441% | 83.81% |

All baseline/H2/dense streams decoded bit-exactly and passed SHA verification.

## Interpretation

H2 is materially better than H1:
- H1 recovered 76.78% of dense gain;
- H2 recovers 88.23%;
- candidate evaluations rise only from ~30.9 to ~35.5/block.

The remaining quality gap is concentrated in mobile, football and stefan.
This suggests that the exhaustive optimum often lies near one of the top few sparse candidates,
but not always near the top two.

## Decision

**Do not promote H2 yet.**

It misses the 90% quality-recovery gate by only 1.77 percentage points, while remaining
well below exhaustive dense search cost.

## Next experiment

**KSV-20 H3 — Top-3 Sparse Refinement**

Evaluate:
- all 25 sparse-even candidates;
- union of unique 3x3 integer neighborhoods around the top three sparse vectors.

Promotion-direction target:
- >=90% of KSV-17 dense gain;
- <=80% of dense research cost;
- materially below 81 candidate evaluations/block;
- bit-exact decode with unchanged K17D decoder.
