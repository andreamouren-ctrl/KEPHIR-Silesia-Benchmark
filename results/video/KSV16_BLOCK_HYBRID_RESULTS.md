# KSV-16 — Block Hybrid Inter/Intra Prediction

Date: 2026-09-26
GitHub Actions run: 36234608098
Status: PASS / RESEARCH CHECKPOINT / NO PRODUCTION PROMOTION

## Goal

Test whether AURORA Media's natural-video gap is caused by forcing every 8x8 block
to remain temporally predicted even when a local spatial predictor is better.

Per luma block:
- codes 0..24: existing MC8R4 inter;
- code 25: block-local horizontal intra;
- code 26: block-local vertical intra.

Chroma follows the selected luma mode on the corresponding 4x4 block.

The experiment tests:
- intra penalties 0, 128 and 512;
- MOD8 and ZZ_INTER;
- final candidate selection after KHEPRI EXP-40 compression.

All baseline/hybrid/hybrid-only streams decode bit-exactly and pass SHA verification.

## Results

| Source | Baseline | Hybrid | Delta |
|---|---:|---:|---:|
| container | 3,615,784 | 3,615,618 | -0.0046% |
| coastguard | 4,869,065 | 4,868,861 | -0.0042% |
| mobile | 6,030,139 | 6,022,155 | -0.1324% |
| football | 5,870,396 | 5,807,522 | **-1.0710%** |
| stefan | 4,397,098 | 4,393,756 | -0.0760% |

Aggregate:
- baseline: **24,782,482 bytes**
- hybrid: **24,707,912 bytes**
- gain: **74,570 bytes / 0.3009%**
- hybrid-only: 24,707,980 bytes

All five sources improve, but the aggregate opportunity is small.

## Mode-selection evidence

The winning hybrid windows overwhelmingly use **penalty 0**.

Approximate winning intra fractions:
- container: effectively 0%;
- coastguard: ~0.01–0.04%;
- mobile: ~0.71–1.20%;
- football: ~2.74%, 9.90%, 8.96%;
- stefan: ~4.17% in one window, ~0.16–0.21% in the others.

This is useful evidence:
- spatial escape modes genuinely help difficult football regions;
- the improvement is localized;
- conservative penalties are not the main limitation;
- simple horizontal/vertical intra prediction is not powerful enough to close the natural-video gap.

## Decision

**Do not promote KSV-16 into the production codec.**

Keep the result as research evidence.

Combined natural-corpus maximum/observed opportunities:
- KSV-13 wider radius: ~0.73%;
- KSV-14 global + local motion: ~0.81%;
- KSV-15 dual temporal reference: ~0.85%;
- KSV-16 block inter/intra: ~0.30%.

The next experiment should examine the granularity of the base motion field itself.

## Key discovery for KSV-17

The current Python MC8R4 candidate generator is:

`range(-radius, radius + 1, 2)`

At radius 4 the search therefore tests only:

`{-4, -2, 0, +2, +4}`

on each axis — **25 vectors total**.

Odd integer displacements are never evaluated.

## Next experiment

**KSV-17 — Dense Integer Motion**

Compare:
- current sparse-even MC8R4: 25 candidates;
- dense integer MC8R4: all dx/dy in [-4,+4], 81 candidates.

Important property:
81 candidates still fit in one byte, so the motion-map storage remains one byte per block.

Research questions:
- final KHEPRI byte gain on the natural corpus;
- gain concentration on football/stefan/coastguard/mobile;
- CPU/search cost increase;
- whether a later hierarchical shortlist can recover dense-search quality at bounded cost.
