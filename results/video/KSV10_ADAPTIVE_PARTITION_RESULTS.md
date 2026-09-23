# KSV-10 — Adaptive 16x16 / 8x8 Motion Partition

Date: 2026-09-23
GitHub Actions run: 35854347578
Backend: KHEPRI EXP-37A
Status: PASS / CONDITIONAL RESEARCH ONLY

## Purpose

Test adaptive motion partitioning:
- one 16x16 motion vector;
- or split into four 8x8 motion vectors.

Three split penalties were tested:
- 0
- 256
- 1024

All variants were lossless and SHA-verified.

## Best observations

### Akiyo
MC8R4:
- 2,209,685 bytes

Best adaptive:
- AP256: 2,210,033 bytes

Delta:
- +348 bytes
- +0.0157%

### Foreman
MC8R4:
- 5,779,453 bytes

Best adaptive:
- AP256: 5,779,697 bytes

Delta:
- +244 bytes
- +0.0042%

### Bus
MC8R4:
- 1,841,864 bytes

Best adaptive:
- AP256: **1,840,161 bytes**

Delta:
- **-1,703 bytes**
- **-0.0925%**

## Decision

Do not replace MC8R4 globally.

Retain AP256 only as a candidate for high-motion content.

The experiment confirms that adaptive partitioning can help the high-motion Bus sequence, but its metadata/partition cost slightly hurts lower-motion material.

Next step:
activate AP256 only behind a cheap high-motion classifier and test it per 20-frame routing window.
