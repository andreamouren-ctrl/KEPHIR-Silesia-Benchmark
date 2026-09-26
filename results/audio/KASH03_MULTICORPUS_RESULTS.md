# KASH-03 Unseen Multi-Corpus Validation

Date: 2026-09-26
GitHub Actions run: 36224815221
Status: PASS / NO PRODUCTION PROMOTION

## Goal

Validate the frozen KASH-02 recovery-horizon rule on unseen lossless film-audio sources
without retraining.

Frozen KASH-02 rule:
- feature: diff_change
- operator: >=
- threshold: 2.0409084219

Unseen sources:
- Elephants Dream
- Big Buck Bunny
- Tears of Steel

Each source was normalized to:
- stereo
- 48 kHz
- signed 16-bit PCM
- 30-second validation segment

All fixed, oracle and predictor outputs were bit-exact.

## Aggregate

Fixed 2-second baseline:
- **8,966,978 bytes**

Research oracle:
- **8,882,472 bytes**
- available adaptive gain: **84,506 bytes**

Frozen KASH-02 predictor:
- **8,959,223 bytes**
- gain versus fixed 2 s: **7,755 bytes**
- approximately **0.0865%**
- oracle gain recovered: **9.177%**

Production candidate duplicate encodes:
- **0**

## Per-source results

### Elephants Dream
- fixed: 2,404,109 bytes
- oracle: 2,403,949 bytes
- predictor: 2,404,972 bytes
- predictor regression: **+863 bytes**
- delta: **+0.035897%**
- oracle recovery: negative due to false split cost

### Big Buck Bunny
- fixed: 3,138,666 bytes
- oracle: 3,074,781 bytes
- predictor: 3,138,666 bytes
- predictor gain: **0 bytes**
- oracle opportunity missed: **63,885 bytes**

### Tears of Steel
- fixed: 3,424,203 bytes
- oracle: 3,403,742 bytes
- predictor: 3,415,585 bytes
- predictor gain: **8,618 bytes**
- delta: **-0.251679%**
- oracle gain recovered: **42.119%**

## Decision

**Do not promote the frozen KASH-02 rule to production.**

The experiment proves two things:

1. adaptive recovery horizon has real compression value across multiple unseen sources;
2. the single-feature Sintel-derived rule does not generalize reliably enough.

The most important signal is Big Buck Bunny:
the oracle exposes a large recovery opportunity that the frozen predictor completely misses.

## Next research direction

KASH-04 must stop treating the problem as a single-feature threshold.

Required direction:
- train/validate across multiple source families;
- use leave-one-source-out validation;
- favor conservative false-split cost;
- allow a small deterministic feature vector;
- keep decision cost far below a real candidate encode;
- preserve zero duplicate production encodes.

The target is not maximum oracle recovery on training data.
The target is robust positive gain on unseen sources with no material per-source regression.
