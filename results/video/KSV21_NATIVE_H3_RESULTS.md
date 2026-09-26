# KSV-21 — Native H3 Dense Motion Core

Date: 2026-09-26
GitHub Actions run: 36237741991
Status: PASS / NATIVE CORE PROMOTED

## Goal

Move the KSV-20 H3 motion-search architecture from Python R&D into the native C++ AURORA Media core.

Implemented:
- canonical 81-vector dense integer candidate ordering;
- 25-vector sparse-even coarse stage;
- exact top-3 ranking by luma SAD + dense-index tie order;
- union of unique 3x3 integer neighborhoods around the top three sparse candidates;
- FLOOR and TRUNC YUV420 chroma policies;
- one-byte dense motion map;
- dense decoder;
- SIMD residual path reuse.

## Python <-> C++ conformance

Reference case:
- 256x240;
- 960 blocks;
- Python and C++ fingerprints matched exactly.

Shared fingerprints:
- motion: **9706599797137296288**
- FLOOR residual: **7515481718988465414**
- TRUNC residual: **17998074391751338452**

Odd-displacement blocks:
- **498 / 960**

An additional direct binary-vector test compared the generated Python motion map and both residual buffers byte-for-byte against C++:
- 128x96;
- 192 blocks;
- 164 odd-displacement blocks;
- result: **PASS**

## Native 4K H3 motion-stage scaling

Synthetic 3840x2160 frame pair, tiled through the current AURORA 4K planner.

Sparse MC8R4 reference, 4 workers:
- **0.0112414 s**
- **88.9572 fps** motion stage

Native H3:

| Workers | Seconds | Motion-stage fps |
|---:|---:|---:|
| 1 | 0.103478 | 9.6639 |
| 2 | 0.0506373 | 19.7483 |
| 4 | **0.0362169** | **27.6114** |
| 8 | 0.0375178 | 26.6540 |

All worker counts generated the same H3 fingerprint:
- **588292038902737796**

## Interpretation

Native H3 is correct and scales well to four workers on the CI runner.

The motion stage is substantially more expensive than sparse MC8R4:
- H3 4-worker time / sparse 4-worker time: approximately **3.22x**

However, prior full-pipeline profiling showed KHEPRI dominates total encode cost, so the motion-stage slowdown must be evaluated inside the complete EXP-40 pipeline rather than judged in isolation.

## Decision

**Promote the native H3 core.**

Do not yet replace the full production routing path.

The remaining product problem is policy selection:
- FLOOR vs TRUNC chroma;
- MOD8 vs ZZ_INTER residual mapping;
- avoid four KHEPRI candidate encodes.

## Next checkpoint

**KSV-22 — H3 Production Policy Selector**

Use cheap residual statistics/entropy estimates to select:
- chroma rounding policy;
- residual mapping;

before a single KHEPRI encode.

Then validate:
- natural-corpus bytes against KSV-20 H3 oracle;
- decision cost;
- full native 4K throughput;
- no duplicate production candidate encodes.
