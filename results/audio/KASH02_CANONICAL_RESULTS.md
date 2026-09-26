# KASH-02 Canonical Recovery Predictor Results

Date: 2026-09-26
GitHub Actions run: 36224542571
Status: PASS / RESEARCH CANDIDATE

## Baseline

Canonical AURORA audio frontend:
- PCM s16le stereo 48 kHz
- KMRL carry prediction
- FULL256
- TAIL16
- KHEPRI EXP-37A
- AUM v0.1

Fixed 2-second recovery baseline:
- **5,546,982 bytes**
- bit-exact

## Oracle

Research-only 1 s / 2 s dynamic-programming oracle:
- **5,541,642 bytes**

Oracle gain versus fixed 2 s:
- **5,340 bytes**
- approximately **0.0963%**

Oracle candidate-search time:
- **27.475330 s**

The oracle is not a production path because it requires duplicate candidate encodes.

## Cheap PCM predictor

Selected rule:
- feature: `diff_change`
- operator: `>=`
- threshold: `2.0409084219`
- blocked-CV weighted accuracy: **0.926604**
- blocked-CV accuracy: **0.881410**

Final predictor:
- **5,543,634 bytes**
- bit-exact
- production duplicate candidate encodes: **0**

Gain versus fixed 2 s:
- **3,348 bytes**
- approximately **0.0604%**

Oracle gain recovered:
- **62.697%**

Decision cost:
- predictor PCM decision: **0.039369 s**
- oracle search: **27.475330 s**
- predictor decision is approximately **698x cheaper** than oracle search.

## Interpretation

KASH-02 proves that a cheap PCM-domain rule can recover a meaningful fraction of the
adaptive recovery-horizon gain without running duplicate production encodes.

This is strategically important because recovery-point density directly affects:
- random access;
- stream recovery after loss/corruption;
- seek latency;
- compression-state reset cost.

However, the rule was discovered and evaluated on the same source family.

## Decision

**Do not promote the rule to production yet.**

Promote KASH-02 as a research result and move to KASH-03:
- freeze candidate features/rule-selection procedure;
- evaluate on multiple unseen music, speech and mixed-program sources;
- measure compression gain, false split cost and decision overhead;
- production promotion requires positive aggregate gain without catastrophic per-source regressions.
