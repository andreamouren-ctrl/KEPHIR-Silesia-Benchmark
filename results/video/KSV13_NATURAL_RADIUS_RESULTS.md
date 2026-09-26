# KSV-13 — Natural Motion Radius Sweep

Date: 2026-09-26
GitHub Actions run: 36229152022
Status: PASS / NO GLOBAL R6 PROMOTION

## Goal

Measure whether AURORA Media's natural-video gap is primarily caused by the current
MC8R4 ±4-pixel motion-search radius.

For every 20-frame routing window, the research router evaluates:
- TEMP;
- MC R4 MOD8;
- MC R4 ZZ_INTER;
- MC R6 MOD8;
- MC R6 ZZ_INTER.

It emits and independently verifies three streams:
- R4 policy: best TEMP/R4 candidate;
- R6 policy: best TEMP/R6 candidate;
- ORACLE: best of all five candidates.

All streams decoded bit-exactly and passed SHA verification.

## Results

| Source | R4 bytes | R6 bytes | Oracle bytes | R6 vs R4 |
|---|---:|---:|---:|---:|
| container | 3,615,787 | 3,616,932 | 3,615,787 | +0.0317% |
| coastguard | 4,869,068 | 4,870,396 | 4,869,068 | +0.0273% |
| mobile | 6,030,142 | 6,032,867 | 6,030,142 | +0.0452% |
| football | 5,870,399 | **5,746,647** | **5,746,647** | **-2.1081%** |
| stefan | 4,397,101 | **4,340,057** | **4,340,057** | **-1.2973%** |

Aggregate:
- R4: **24,782,497 bytes**
- R6: **24,606,899 bytes**
- ORACLE: **24,601,701 bytes**
- R6 vs R4: **-0.7086%**
- ORACLE vs R4: **-0.7295%**

## Interpretation

A wider motion radius is useful on the two clearly stronger-motion sources, especially football.

However:
- low/camera/texture sources do not benefit;
- the ideal per-window R4/R6 oracle adds only ~0.021 percentage points beyond global R6;
- the total compression opportunity is below 1%;
- R6 nearly doubles the raw candidate grid from 25 to 49 vectors per block.

Therefore the current natural-content gap is not primarily caused by the ±4 radius.

## Decision

**Do not promote global MC8R6.**

Do not spend the next development cycle on a complex R4/R6 classifier: even a perfect
classifier can recover only ~0.73% on this corpus.

The next experiment must change the prediction model rather than only enlarging the same search.

## Next experiment

**KSV-14 — Global Translation + Local Motion**

Research hypothesis:
- estimate a cheap frame-level translation over a much wider field;
- encode that global displacement explicitly;
- run the existing compact local ±4 search around the global vector;
- preserve TEMP fallback and residual-mode routing.

Target content:
- camera pans;
- coherent scene translation;
- high-motion sequences where the correct displacement lies outside the local ±4 field.

This can access wide displacement without paying a 49+ candidate search on every block.
