# KSV-05 — Adaptive Routing Horizon

Date: 2026-09-23  
GitHub Actions runs:
- initial 10-frame router: 35834533728
- 20/30/50-frame sweep: 35834848430

Backend: **KHEPRI EXP-37A**  
Result: **PASS / 20-FRAME ROUTING HORIZON PROMOTED**

All outputs reconstructed bit-exactly.

## Purpose

Remove manual per-clip mode selection. AURORA now evaluates its current reversible
video paths over bounded routing windows and stores the path that produces the
smaller final KHEPRI payload.

Current paths:
- TEMP: reversible temporal residual;
- MC8R4: reversible bounded motion-compensated residual.

Generic mode selection by final compressed size is BACKGROUND engineering and
is not claimed as candidate IP.

## Results

| Routing horizon | Akiyo | Foreman | Bus | Aggregate |
|---|---:|---:|---:|---:|
| 10 frames | 2,245,835 | **5,763,339** | **1,839,276** | 9,848,450 |
| **20 frames** | **2,175,347** | 5,768,334 | 1,841,147 | **9,784,828** |
| 30 frames | 2,200,618 | 5,772,450 | 1,842,393 | 9,815,461 |
| 50 frames | 2,190,520 | 5,774,355 | 1,841,725 | 9,806,600 |

Prior best AURORA result using manual whole-clip choice:
- 9,829,974 bytes

FFV1 aggregate on same three clips:
- 10,357,351 bytes

## Milestone

The 20-frame router produces:
- **45,146 fewer bytes (-0.459%)** than the prior manually selected AURORA aggregate;
- **572,523 fewer bytes (-5.528%)** than FFV1 aggregate on this three-clip research corpus.

Per clip versus the previous best AURORA whole-clip path:
- Akiyo: 2,208,653 -> **2,175,347** (-1.508%)
- Foreman: 5,779,455 -> **5,768,334** (-0.192%)
- Bus: 1,841,866 -> **1,841,147** (-0.039%)

## Routing decisions at 20 frames

Akiyo:
- TEMP: 14 windows
- MC8R4: 1 window

Foreman:
- TEMP: 3 windows
- MC8R4: 12 windows

Bus:
- TEMP: 0 windows
- MC8R4: 4 windows

This is important because the encoder is now making content-dependent decisions
internally rather than relying on an external/manual clip classification.

## Interpretation

The strong Akiyo gain indicates that KHEPRI's state/reset horizon itself matters:
breaking a long stationary residual stream into moderate independent windows can
improve final compression despite added container/reset overhead.

That observation motivates a new proprietary research direction:
**KHEPRI Adaptive State Horizon (KASH)** — a future mechanism in which reset
horizon is derived from KHEPRI-specific residual-state behavior rather than a
fixed frame count.

KASH is only a research hypothesis at this stage. Fixed segmentation and generic
adaptive chunking are not claimed as inventions.

## Decision

Promote:
- adaptive TEMP/MC8R4 routing infrastructure;
- **20-frame routing horizon** as the current video baseline for this corpus;
- EXP-37A as backend.

Next checkpoint should investigate KHEPRI-specific state-horizon adaptation
without copying established codec mode-decision schemes.
