# KSV-14 — Global Translation + Local Motion

Date: 2026-09-26
GitHub Actions run: 36230538594
Status: PASS / RESEARCH CHECKPOINT / NO PRODUCTION PROMOTION

## Goal

Test whether a cheap wide-field frame translation plus the existing local ±4 block search
can materially improve AURORA Media on natural camera/high-motion content.

Model:
- sparse luma global translation search over ±24 pixels;
- one global vector per inter frame;
- local ordered 25-candidate ±4 search around the global vector;
- absolute zero-motion fallback for border blocks;
- MOD8 and ZZ_INTER residual candidates;
- TEMP fallback;
- final decision based on KHEPRI EXP-40 bytes.

All emitted baseline/global-local/oracle streams decoded bit-exactly and passed SHA verification.

## Results

| Source | Baseline | Global+Local | Oracle | Global+Local vs baseline |
|---|---:|---:|---:|---:|
| container | 3,615,784 | 3,617,170 | 3,615,784 | +0.0383% |
| coastguard | 4,869,065 | 4,870,209 | 4,869,065 | +0.0235% |
| mobile | 6,030,139 | 6,030,625 | 6,030,139 | +0.0081% |
| football | 5,870,396 | **5,758,413** | **5,758,413** | **-1.9076%** |
| stefan | 4,397,098 | **4,307,403** | **4,307,311** | **-2.0399%** |

Aggregate:
- baseline: **24,782,482 bytes**
- global-local: **24,583,820 bytes**
- oracle: **24,580,712 bytes**
- global-local gain: **0.8016%**
- maximum oracle gain: **0.8142%**

## Decision

**Do not promote KSV-14 to the production baseline.**

The model is valid and useful on the two strongest-motion sources, but the total opportunity remains
below 1% on the natural corpus. That is not enough to justify a new frame syntax, new global-vector
metadata and additional global-motion estimation in the default codec path.

## Engineering interpretation

KSV-13 and KSV-14 together provide a strong negative result:

- wider search radius alone: max ~0.73% aggregate opportunity;
- global translation + local search: max ~0.81% aggregate opportunity.

Therefore the major natural-video compression gap is not primarily caused by search radius or
missing one global pan vector.

The next predictor experiment must add **temporal reference diversity**.

## Next experiment

**KSV-15 — Dual-Reference Temporal Motion**

Research plan:
- reference 0: immediately previous decoded frame;
- reference 1: frame two positions back when available;
- same local MC8R4 search for each reference;
- explicit reference selection;
- TEMP fallback;
- MOD8 and ZZ_INTER residual mappings;
- baseline, dual-reference and oracle streams all independently decoded/SHA verified.

Promotion threshold:
- do not consider production integration unless aggregate natural-corpus gain is materially larger
  than KSV-13/KSV-14 and no low-motion source suffers a significant regression.
