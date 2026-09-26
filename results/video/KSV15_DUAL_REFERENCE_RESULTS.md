# KSV-15 — Dual-Reference Temporal Motion

Date: 2026-09-26
GitHub Actions run: 36231942150
Status: PASS / RESEARCH CHECKPOINT / NO PRODUCTION PROMOTION

## Goal

Measure whether AURORA Media's natural-video compression gap is caused by forcing every
inter block to use only the immediately previous frame.

KSV-15 adds one second already-decoded reference:
- ref0: previous frame;
- ref1: frame two positions back inside the GOP.

Each 8x8 luma block searches the same ordered MC8R4 candidate set on both references.
Reference selection is encoded directly in the one-byte motion map:
- 0..24 = ref0;
- 25..49 = ref1.

Equal-SAD ties prefer ref0.

All baseline/dual/oracle streams decoded bit-exactly and passed SHA verification.

## Results

| Source | Baseline | Dual-reference | Oracle | Dual vs baseline |
|---|---:|---:|---:|---:|
| container | 3,615,784 | 3,618,777 | 3,615,784 | +0.0828% |
| coastguard | 4,869,065 | 4,870,378 | 4,869,065 | +0.0270% |
| mobile | 6,030,139 | **5,860,681** | **5,860,681** | **-2.8102%** |
| football | 5,870,396 | **5,845,982** | **5,845,982** | **-0.4159%** |
| stefan | 4,397,098 | **4,379,546** | **4,379,546** | **-0.3992%** |

Aggregate:
- baseline: **24,782,482 bytes**
- dual-reference: **24,575,364 bytes**
- oracle: **24,571,058 bytes**
- dual-reference gain: **0.8357%**
- maximum oracle gain: **0.8531%**

## Decision

**Do not promote KSV-15 into the production codec.**

The model clearly helps the texture/pan source (mobile), proving that temporal reference diversity
has real value, but the aggregate opportunity remains below 1% and the strongest high-motion
source improves only ~0.42%.

## Combined conclusion from KSV-13 / KSV-14 / KSV-15

Natural-corpus maximum opportunities:

- wider local radius: ~0.73%
- global translation + local motion: ~0.81%
- dual temporal reference: ~0.85%

These experiments rule out three obvious motion-search limitations as the dominant explanation
for AURORA's natural-video gap.

The next model should stop forcing temporal prediction where temporal prediction is locally poor.

## Next experiment

**KSV-16 — Block Hybrid Inter/Intra**

For every 8x8 block:
- existing MC8R4 inter candidate;
- block-local horizontal spatial predictor;
- block-local vertical spatial predictor.

Use reserved motion-map codes for spatial modes, so the mode map remains one byte per block.
Test conservative intra penalties and both MOD8 / ZZ_INTER residual mappings.

Target:
- occlusions;
- newly revealed image regions;
- high-detail texture;
- fast/non-coherent motion where even the best temporal reference remains poor.
