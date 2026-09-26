# KSV-23 — Native One-Pass H3 Residual Variants

Date: 2026-09-26
GitHub Actions run: 36243748939
Status: PASS / PROMOTION CANDIDATE

## Goal

Avoid repeating native H3 motion search merely to materialize both YUV420 chroma-rounding variants needed by the production policy selector.

The native API now computes one canonical H3 dense motion map plus both FLOOR and TRUNC YUV420 residuals in a single motion-search pass.

## Correctness

Existing KSV-21 native H3 regression:
- blocks: 960
- odd-displacement blocks: 498
- motion fingerprint: 9706599797137296288
- FLOOR residual fingerprint: 7515481718988465414
- TRUNC residual fingerprint: 17998074391751338452
- result: PASS

One-pass variants were compared against two independent H3 calls:
- motion maps identical;
- FLOOR residual byte-identical;
- TRUNC residual byte-identical;
- both residual variants decode exactly;
- result: PASS

## Performance

256x240 benchmark, 12 loops:
- one-pass FLOOR+TRUNC: **0.905197 ms**
- two independent H3 searches: **1.81554 ms**
- speedup: **2.00568x**

Promotion gate:
- required >=1.50x
- measured 2.00568x
- PASS

## Decision

**Promote KSV-23 native H3 variants infrastructure.**

This is not a compression-mode decision itself. It removes duplicated motion-search work and provides the efficient native primitive needed by the final H3 production selector.

## Next step

KSV-24 must focus on MOD8 versus ZZ_INTER selection. KSV-22 already selected the oracle chroma policy on all 15 natural-corpus windows.

KSV-24 should:
- keep the selected chroma residual;
- select MOD8/ZZ using cheap residual-domain statistics;
- perform exactly one KHEPRI encode;
- target >=95% of KSV-20 H3 oracle gain and <=0.10% aggregate penalty.
