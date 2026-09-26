# AURORA Media EXP-41 Parser Profile

Date: 2026-09-26
GitHub Actions run: 36234763711
Status: PASS / PROFILING CHECKPOINT

## Goal

Measure how much EXP-40 already removes duplicated match-search work between
`findbest` and `findpred`, and identify the next exact-speed target.

Corpus:
- current synthetic mapped 4K residual corpus;
- 135 tiles;
- 12,441,600 input bytes;
- roundtrip verified.

## Counters

- findbest calls: **118,249**
- findpred calls: **118,249**
- findbest chain nodes: **3,085,182**
- findpred chain nodes: **3,571,938**
- findbest early stops: **25,774**
- shared-cache hits: **3,085,182**
- shared-cache misses: **360,200**
- predictive match computations: **360,200**
- predictive scored candidates: **1,257,946**

Derived:
- findpred node cache reuse: **86.3728%**
- findpred nodes requiring a fresh match computation: **10.0842%**
- findbest calls ending through historical early-stop rules: **21.7964%**

## Interpretation

EXP-40 already captures nearly the entire overlapping prefix between the two match searches.

The remaining gap is not primarily "more of the same cache":
- 3.085M of 3.572M findpred node visits reuse prior work;
- only 360k visits perform a fresh predictive match computation;
- 1.258M candidates still execute predictive scoring/cost logic.

Therefore the next exact-speed experiment should profile and reduce:
- `dualLcost` / literal-prefix cost work;
- repeated `log2(distance+1)` evaluation;
- branch/candidate scoring overhead;
- memory locality for the unmatched predictive tail.

## Decision

EXP-41 is a profiler only. No wire-format or parser decision change is promoted.

Next backend experiment should preserve K37M byte identity and target scoring/cost evaluation rather than simply enlarging the shared match cache.
