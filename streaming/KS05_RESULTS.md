# KS-05 — KTARP Topology-Adaptive Permutation

Date: 2026-09-23
GitHub Actions run: 35813682748
Result: **PASS technically / NOT PROMOTED**

Source: same 52 s Sintel-derived stereo s16le 48 kHz PCM.

| Variant | Final bytes | % PCM | vs FULL256 |
|---|---:|---:|---:|
| KMRL1 FULL256 row-major | **5,552,105** | **55.610%** | baseline |
| KTARP fixed transpose | 5,824,470 | 58.338% | +4.906% |
| KTARP equal-affinity | 5,729,116 | 57.383% | +3.188% |
| KTARP run-affinity | 5,596,006 | 56.050% | +0.791% |
| FLAC -5 block 960 | 4,730,170 | 47.378% | -14.804% |

All variants were bit-exact.

## Decision

KTARP is **not promoted**. The best topology-adaptive heuristic failed to beat the fixed FULL256 baseline, so it does not qualify as a technical core or candidate invention in its present form.

The experiment remains useful negative evidence:
- row-major residual planes are already better matched to EXP-33H than the tested alternative permutations;
- a heuristic based only on byte equality at favored distances is not a sufficient proxy for final KHEPRI compressed size;
- any future topology-adaptive mechanism must use a materially better cost model or a different transform family.
