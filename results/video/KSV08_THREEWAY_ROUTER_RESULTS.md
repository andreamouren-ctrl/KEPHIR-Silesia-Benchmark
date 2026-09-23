# KSV-08 — Three-Way Adaptive Router

Date: 2026-09-23
GitHub Actions run: 35849811370
Backend: KHEPRI EXP-37A
Result: PASS / PROMOTED

## Modes

For each 20-frame routing window, AURORA evaluates final KHEPRI bytes for:
- TEMP
- MC8R4 + MOD8 residual symbols
- MC8R4 + ZZ_INTER residual symbols

The smallest final backend payload is selected.

All outputs are bit-exact.

## Results

### Akiyo
- 2,130,625 bytes
- modes: TEMP 0 / MC_MOD8 0 / MC_ZZ_INTER 15

Previous KSV-05 baseline:
- 2,175,347 bytes

Gain:
- 44,722 bytes
- -2.056%

### Foreman
- 5,754,115 bytes
- modes: TEMP 0 / MC_MOD8 6 / MC_ZZ_INTER 9

Previous KSV-05:
- 5,768,334 bytes

Gain:
- 14,219 bytes
- -0.247%

### Bus
- 1,841,147 bytes
- modes: TEMP 0 / MC_MOD8 4 / MC_ZZ_INTER 0

Previous KSV-05:
- 1,841,147 bytes

Gain:
- 0 bytes

## Aggregate

KSV-05:
- 9,784,828 bytes

KSV-08:
- **9,725,887 bytes**

Improvement:
- **58,941 bytes**
- **-0.602%**

FFV1 aggregate reference:
- 10,357,351 bytes

KSV-08 is approximately:
- **6.10% smaller than FFV1** on the current three-clip diagnostic corpus.

This is not a general superiority claim; the corpus is small.

## Decision

Promote KSV-08 as the current AURORA lossless video research baseline.

The important result is content dependence:
- low-motion Akiyo strongly prefers ZZ_INTER;
- Foreman mixes MOD8 and ZZ_INTER;
- high-motion Bus rejects ZZ_INTER and stays on MOD8.

Therefore residual-symbol mapping is now a routed codec decision rather than a fixed transform.
