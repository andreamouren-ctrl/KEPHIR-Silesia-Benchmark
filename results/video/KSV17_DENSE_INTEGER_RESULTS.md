# KSV-17 — Dense Integer Motion

Date: 2026-09-26
GitHub Actions run: 36235092271
Status: PASS / RESEARCH CHECKPOINT / PROMISING, NOT YET PRODUCTION

## Goal

Test whether AURORA Media loses natural-video compression because the current MC8R4 search
samples motion every two luma pixels and therefore never evaluates odd integer displacement.

Current sparse MC8R4:
- values: {-4,-2,0,+2,+4}
- 25 candidates/block

KSV-17 dense MC8R4:
- values: every integer in [-4,+4]
- 81 candidates/block
- motion map remains one byte/block

Two deterministic chroma policies were tested:
- FLOOR: d//2
- TRUNC: int(d/2)

Both MOD8 and ZZ_INTER were evaluated after KHEPRI EXP-40 compression.

All baseline/dense/oracle streams decoded bit-exactly and passed SHA verification.

## Results

| Source | Baseline | Dense | Oracle | Dense vs baseline |
|---|---:|---:|---:|---:|
| container | 3,615,784 | 3,616,370 | 3,615,675 | +0.0162% |
| coastguard | 4,869,065 | 4,796,319 | 4,796,319 | **-1.4940%** |
| mobile | 6,030,139 | 5,681,252 | 5,681,252 | **-5.7857%** |
| football | 5,870,396 | 5,836,922 | 5,836,922 | **-0.5702%** |
| stefan | 4,397,098 | 4,333,601 | 4,333,601 | **-1.4441%** |

Aggregate:
- baseline: **24,782,482 bytes**
- dense: **24,264,464 bytes**
- oracle: **24,263,769 bytes**
- dense improvement: **518,018 bytes / 2.0903%**
- maximum oracle improvement: **518,713 bytes / 2.0931%**

The dense policy is therefore within only 695 bytes of the full sparse+dense oracle.

## Odd-displacement evidence

Mean fraction of blocks selecting a motion vector with at least one odd component:

- container: **7.10%**
- coastguard: **36.63%**
- mobile: **67.48%**
- football: **46.62%**
- stefan: **29.14%**

This strongly confirms that the sparse-even search is discarding useful motion information.

The effect is especially large on texture/pan content:
- mobile improves by 5.79%;
- more than two thirds of blocks use at least one odd motion component.

## Cost

Research encode cost on the 5-source corpus:
- baseline candidate search/encode path: **64.257 s**
- dense path: **161.367 s**

Dense research cost is approximately **2.51x** baseline.

Per-source dense search alone:
- container: 28.53 s
- coastguard: 28.48 s
- mobile: 28.33 s
- football: 28.41 s
- stefan: 23.46 s

This is not acceptable as a production search strategy.

## Decision

**Do not promote exhaustive 81-candidate dense search directly into production.**

However, unlike KSV-13/14/15/16, KSV-17 shows a material compression opportunity:
- aggregate gain >2%;
- very large gain on mobile;
- improvement on four of five sources;
- oracle is essentially identical to dense.

Therefore dense integer motion becomes the new quality target.

## Next experiment

**KSV-18 — Hierarchical Dense Refinement**

Design:
1. run the existing 25 sparse-even candidates;
2. take the best sparse vector;
3. evaluate only its odd/even 1-pixel neighborhood;
4. preserve the same 81-code dense motion-map semantics;
5. compare final bytes against exhaustive KSV-17 dense.

Target:
- recover at least 90–95% of the KSV-17 byte gain;
- reduce candidate evaluations substantially below 81/block;
- maintain bit-exact decode;
- keep one-byte motion map.
