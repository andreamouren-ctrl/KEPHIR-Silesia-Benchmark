# KSV-06 — Motion-Field Representation

Date: 2026-09-23
GitHub Actions run: 35845593500
Backend: KHEPRI EXP-37A
Result: PASS / NO PROMOTION

## Purpose

Test whether a smaller or more structured representation of MC8R4 motion vectors improves final KHEPRI compression.

The motion search and residual field were held constant.

Variants:
- RAW8: one candidate-index byte per block
- INDEX5: candidate index packed to 5 bits
- XY3_SPLIT: dx and dy encoded as separate 3-bit planes

All variants decoded bit-exactly.

## Results

### Akiyo
- RAW8: 2,209,366 bytes
- INDEX5: 2,209,295 bytes (-71 / -0.0032%)
- XY3_SPLIT: 2,211,484 bytes (+2,118 / +0.0959%)

### Foreman
- RAW8: 5,779,294 bytes
- INDEX5: 5,783,239 bytes (+3,945 / +0.0683%)
- XY3_SPLIT: 5,794,631 bytes (+15,337 / +0.2654%)

### Bus
- RAW8: 1,841,829 bytes
- INDEX5: 1,843,464 bytes (+1,635 / +0.0888%)
- XY3_SPLIT: 1,844,974 bytes (+3,145 / +0.1708%)

## Decision

Keep RAW8 as the current MC8R4 motion-map representation.

Do not promote INDEX5 or XY3_SPLIT.

## Scientific interpretation

Both alternative layouts reduce the frontend byte count, but final KHEPRI output becomes worse on motion-heavy clips.

This reinforces the project rule:

frontend size is not the optimization target; final KHEPRI archive size is.

The next video work should therefore change the motion/residual model itself rather than simply bit-pack the existing motion map.
