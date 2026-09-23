# KHEPRI Stream backend baseline

Date: 2026-09-23

## Active media backend

**KEPHIR EXP-37A PREDICTIVE-DUAL-MATCH**

Build profile:
- K2_ADAPT_MODE=9
- K2_LAZY_MODE=1
- K2_PSG_MODE=3
- K2_DIST_TOPO_MODE=8
- K2_DUAL_MATCH_MODE=1

EXP-37A replaces EXP-33H as the default entropy/compression backend for future KHEPRI Stream media experiments.

## Why not EXP-44 as the default media backend?

EXP-44 Structural Router is currently the best validated general-purpose KHEPRI system in the repository:
- Silesia: 63,581,600 bytes
- ratio: 30.000012%
- lossless SHA validation: PASS

EXP-44 routes 512 KiB chunks among:
- BASE
- delta-lag 4 + transpose 4
- delta-lag 1024 + transpose 1024

On the KMRL FULL256 + TAIL16 real-audio stream, however, EXP-44 selected BASE for all 16 chunks. Its structural transforms therefore duplicated work already performed by the media frontend.

KS-07:
- EXP-33H: 5,543,340 bytes
- EXP-44 router: 5,542,990 bytes
- router modes: [16 BASE, 0 mode-1, 0 mode-2]
- EXP-44 encode cost was much higher because three candidates were tested per chunk.

KS-07B direct-core validation:
- EXP-33H: 5,543,340 bytes
- **EXP-37A: 5,542,167 bytes**
- delta: **-1,173 bytes / -0.02116%**
- SHA: PASS

## Decision

For KHEPRI/AURORA Media:
- use **EXP-37A directly** as the active backend;
- retain the EXP-44 router as an optional research tool for payloads that have not already undergone media-specific structural transformation;
- do not use EXP-45 as a codec backend yet because EXP-45 is an oracle/research surface, not a validated standalone production compressor.

Future codec checkpoints must benchmark against EXP-37A unless a newer validated KHEPRI core beats it on the same media workload.
