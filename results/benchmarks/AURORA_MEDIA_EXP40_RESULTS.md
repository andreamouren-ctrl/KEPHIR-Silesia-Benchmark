# AURORA Media EXP-40 Shared Match Cache Results

Date: 2026-09-26
GitHub Actions run: 36226718173
Status: PASS / PROMOTE AS TRANSPARENT K37M ENCODER OPTIMIZATION

## Goal

Reduce duplicated EXP-37 match-length work without changing parser decisions or the K37M wire format.

EXP-40 keeps:
- the historical `findbest` candidate order and early-stop behavior;
- the historical `findpred` traversal depth and scoring;
- the same token decisions;
- the same K37M frame format.

It only reuses match lengths already computed by `findbest` when `findpred`
visits the same chain prefix.

## Hard correctness gate

Repeated A/B on the same mapped 4K residual corpus:

- input bytes: 12,441,600
- packed bytes EXP-37: **126,992**
- packed bytes EXP-40: **126,992**
- payload fingerprint EXP-37: **645283052499814098**
- payload fingerprint EXP-40: **645283052499814098**

Result:

**BITSTREAM_IDENTITY = PASS**

This is stronger than equal compression size: the encoded K37M payload is byte-identical.

## Repeated isolated backend timing

Five alternating trials per backend.

Median encode:
- EXP-37: **436.207 ms**
- EXP-40: **423.404 ms**
- speedup: **1.030x**
- encode time reduction: **2.94%**

Median decode:
- EXP-37: **24.1877 ms**
- EXP-40: **24.1089 ms**
- approximately **0.33% faster**

## Repeated full 4K pipeline timing

Three alternating 4-worker trials.

Median encode:
- EXP-37: **0.165195 s / 6.05345 fps**
- EXP-40: **0.163058 s / 6.13279 fps**
- speedup: **1.0131x**
- encode time reduction: **1.29%**

Median decode:
- EXP-37: **58.3230 fps**
- EXP-40: **57.9247 fps**
- approximately **0.69% slower**

Median combined pipeline:
- EXP-37: **5.48423 fps**
- EXP-40: **5.54564 fps**
- speedup: **1.0112x**
- total time reduction: **1.11%**

Pipeline payload:
- EXP-37: **256,727 bytes**
- EXP-40: **256,727 bytes**

## Decision

**PROMOTE the shared-match cache implementation into the AURORA Media research baseline.**

This does not create a new bitstream version.
K37M remains the wire format.

The gain is moderate rather than transformational, but the change is low-risk because:
- payloads are byte-identical;
- decoder compatibility is unchanged;
- compression ratio is unchanged;
- deterministic behavior is unchanged;
- the optimization targets the measured dominant encoder stage.

## Next backend target

Do not change parser economics.

Next work should profile the EXP-37/EXP-40 parser internally and target exact-cost reductions such as:
- redundant hash work;
- chain-node memory locality;
- repeated logarithm/cost evaluation;
- predictive literal-prefix lookup overhead;
- allocation/vector churn.

Every next backend optimization should preserve K37M identity whenever feasible.
