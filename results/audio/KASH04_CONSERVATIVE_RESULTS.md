# KASH-04 Conservative Macro-Window Results

Date: 2026-09-26
GitHub Actions run: 36225130012
Status: PASS / RESEARCH ONLY / NO PRODUCTION PROMOTION

## Goal

Test whether adaptive audio recovery can be made robust by keeping fixed 2-second macro-window
boundaries and allowing only one local decision:

- keep the window as one 2-second packet; or
- split it into two independent 1-second packets.

This removes the boundary drift present in earlier sequential 1/2-second routing experiments.

## Validation corpus

Four 30-second, stereo 48 kHz, signed-16 lossless source families:
- Sintel
- Elephants Dream
- Big Buck Bunny
- Tears of Steel

All encoded variants decoded bit-exactly.

Production candidate duplicate encodes:
- **0**

## Fit-all diagnostic

Fixed 2-second aggregate:
- **12,133,166 bytes**

Macro-window oracle:
- **12,106,992 bytes**
- available gain: **26,174 bytes**

Final conservative rule:
- activity <= 23.58939561240859
- AND diff_change >= 1.1059252799450545

Predictor aggregate:
- **12,108,096 bytes**
- gain: **25,070 bytes**
- oracle gain recovered: **95.782%**

Per-source gain with the final rule:
- Sintel: 0 bytes
- Elephants Dream: 0 bytes
- Big Buck Bunny: 25,070 bytes
- Tears of Steel: 0 bytes

The fit-all result demonstrates that cheap PCM features contain enough information to identify
large recovery-reset opportunities.

## Leave-one-source-out procedure validation

The rule-selection procedure did **not** generalize safely:

- held-out Sintel: 0 bytes
- held-out Elephants Dream: **-262 bytes**
- held-out Big Buck Bunny: **-232 bytes**
- held-out Tears of Steel: **-18,892 bytes**

Worst held-out regression:
- **18,892 bytes**

Therefore the apparent 95.782% oracle recovery is a fit-all diagnostic, not a production result.

## Decision

**Do not enable adaptive recovery in the production codec.**

Production audio baseline remains:
- canonical FULL256 + TAIL16 frontend;
- fixed 2-second recovery horizon;
- bit-exact AUM packaging.

KASH remains a research subsystem.

The important engineering result is that adaptive recovery has measurable value, but a robust
general predictor requires substantially broader source diversity or a different signal than the
current local PCM feature set.

## Future KASH direction

Do not continue increasing model complexity on this four-source corpus.

Future work must first expand the training/validation corpus across:
- speech;
- music;
- ambience;
- transient-heavy material;
- near-silence;
- highly correlated and weakly correlated stereo;
- multiple sample rates and bit depths.

Only then revisit a tiny deterministic production classifier.
