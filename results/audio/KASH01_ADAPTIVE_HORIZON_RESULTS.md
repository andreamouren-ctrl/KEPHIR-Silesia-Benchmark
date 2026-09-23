# KASH-01 — Adaptive Audio Recovery Horizon

Date: 2026-09-23
GitHub Actions run: 35850770758
Backend: KHEPRI EXP-37A
Result: PASS / RESEARCH VALIDATED / NOT YET PRODUCTION-PROMOTED

## Goal

Test whether the recovery/state horizon itself has content-dependent compression value while keeping the maximum horizon capped at 2 seconds.

Candidates:
- 1 second
- 2 seconds

The experiment minimizes final KHEPRI payload bytes plus AUM packet/index overhead.

All output is lossless and SHA-verified.

## Fixed 2-second baseline

- bytes: 5,546,958
- packets: 26
- SHA: PASS

## Adaptive result

- bytes: **5,541,589**
- packets: 30
- 1-second packets: 8
- 2-second packets: 22
- SHA: PASS

Improvement:
- **5,369 bytes**
- **-0.0968%**

## Interpretation

The optimal path did not choose the maximum 2-second horizon everywhere.

Eight 1-second recovery segments were selected because, at those boundaries, an earlier state reset produced a smaller total KHEPRI representation even after packet/index overhead.

This validates the KASH hypothesis that state-reset placement can be content dependent.

## Why it is not yet production-promoted

The current research implementation obtains the decision by encoding competing 1-second and 2-second candidates and solving the segmentation problem from measured final sizes.

Encoding time:
- fixed 2 s: ~8.68 s
- adaptive research search: ~25.80 s

The current method therefore proves the opportunity but is too expensive as the production decision mechanism.

## Decision

Keep the production audio baseline at fixed 2 seconds for now.

Promote KASH from hypothesis to **validated research direction**.

Next step:
derive a cheap KHEPRI-specific predictor for reset benefit, then test whether it reproduces most of the 5,369-byte gain without duplicate full encodes.
