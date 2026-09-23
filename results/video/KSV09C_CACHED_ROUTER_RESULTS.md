# KSV-09C / KSV-09D — Cheap Mode Prediction and Cached Motion

Date: 2026-09-23

Validation runs:
- KSV-09 predictor dataset: 35851706283
- KSV-09B two-encode router: 35852125332
- KSV-09C cached-motion router: 35852522041
- KSV-09D wall-clock comparison: 35852874674

## Goal

Reduce the brute-force cost of KSV-08, which runs three full KHEPRI candidate encodes per 20-frame window.

## Predictor

A very small predictor was derived from the average signed magnitude of MC residual bytes.

Decision:
- mean signed magnitude < 2.60 -> MC_ZZ_INTER
- otherwise -> MC_MOD8

On 34 diagnostic windows this rule matched the MC oracle on 32 windows.

## Cached-motion architecture

KSV-09C computes MC8R4 motion and residuals once.

The same cached residual field is then used for:
- the cheap mode predictor;
- final serialization as MOD8 or ZZ_INTER.

KHEPRI is therefore run only for:
1. TEMP
2. predicted MC representation

instead of TEMP + MC_MOD8 + MC_ZZ_INTER.

## Compression result

KSV-08 oracle aggregate:
- 9,725,887 bytes

KSV-09C aggregate:
- 9,727,633 bytes

Difference:
- +1,746 bytes
- +0.01795%

## True wall-clock result

KSV-08:
- 62.7543 s

KSV-09C:
- 34.8628 s

Improvement:
- 1.800x speedup
- 44.45% wall-clock reduction

Per clip:
- Akiyo: 43.51% faster, +15 bytes
- Foreman: 44.77% faster, +1,727 bytes
- Bus: 46.58% faster, +4 bytes

## Decision

PROMOTED.

KSV-09C becomes the active operational AURORA Video router.

KSV-08 remains the higher-cost oracle/reference router for research validation.

The promotion criterion is satisfied:
- lossless roundtrip;
- compression within far less than 0.1% of oracle;
- large measured wall-clock reduction.
