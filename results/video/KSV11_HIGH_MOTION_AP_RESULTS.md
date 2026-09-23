# KSV-11 — High-Motion AP256 Gating

Date: 2026-09-23
GitHub Actions run: 35854865283
Status: PASS / PROFILE-SPECIFIC PROMOTION

## Goal

Use the KSV-10 AP256 partition only when motion complexity is high enough to justify it.

Activation signal:
- mean signed MC residual magnitude

Tested thresholds:
- 5.5
- 6.5
- 7.5

## Results

Baseline operational bytes:
- 9,726,391

### Threshold 5.5
- bytes: **9,724,494**
- delta: **-1,897 bytes**
- delta: **-0.01950%**
- activated windows: 5
- AP256 wins: 5/5

### Threshold 6.5
- bytes: 9,724,507
- delta: -1,884 bytes
- activated windows: 4
- AP256 wins: 4/4

### Threshold 7.5
- bytes: 9,725,780
- delta: -611 bytes
- activated windows: 2
- AP256 wins: 2/2

## Decision

Threshold 5.5 is retained for the **Max Compression** profile.

It is not enabled in the Streaming 4K profile because it requires an additional candidate encode on selected high-motion windows.

KSV-09C remains the default operational streaming router.

This gives AURORA two explicit priorities:
- Streaming 4K: bounded work and lower latency;
- Max Compression: additional high-motion search where measured useful.
