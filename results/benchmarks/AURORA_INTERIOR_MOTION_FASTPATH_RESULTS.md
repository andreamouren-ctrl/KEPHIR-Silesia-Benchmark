# AURORA Interior Motion Fast Path Results

Date: 2026-09-26
GitHub Actions run: 36219179822
Status: PASS / PROMOTION CANDIDATE

## Change

MC8R4 now identifies blocks that are at least the search radius from every tile edge.
For those interior blocks, all ordered ±4 motion candidates are guaranteed valid, so the
encoder skips redundant per-candidate boundary checks.

Boundary blocks retain the historical validation path.

Compile-time A/B reference:
`AURORA_DISABLE_INTERIOR_MOTION_FASTPATH`

## Correctness

- existing motion regression test: PASS
- A/B output fingerprints: identical
- motion-map sizes: identical
- residual sizes: identical
- bitstream input equivalence: PASS

The optimization changes no candidate, candidate order, SAD score or tie behavior.

## Native A/B performance

Build:
`-O3 -march=native -mtune=native`

Tile:
- 256 x 240
- YUV420p8
- 80 iterations/scenario

| Scenario | Checked bounds | Interior fast path | Speedup | Time reduction |
|---|---:|---:|---:|---:|
| Static | 0.061097 ms | 0.060889 ms | 1.003x | 0.34% |
| Low motion | 0.103326 ms | 0.096301 ms | **1.073x** | **6.80%** |
| Noise / high activity | 0.177710 ms | 0.151015 ms | **1.177x** | **15.02%** |

## Interpretation

The fast path is naturally close to neutral when the earlier zero-SAD optimization exits on
the first candidate. Its benefit rises as more motion candidates must be evaluated.

This is complementary to the Exact Motion Fast Path:
- Exact Motion Fast Path accelerates easy/perfect matches.
- Interior Motion Fast Path accelerates expensive multi-candidate searches.

## Decision

**PROMOTE.**

The optimization is exact, small, deterministic and has no compression penalty.

## Related rejected experiment: CPU zero-copy tile motion

PR #37 / run 36219053497 validated a direct full-frame region API.

Correctness:
- PASS

4K / 135 tiles:
- legacy encode: 34.421 ms
- direct-region encode: 36.1637 ms
- legacy decode: 28.4831 ms
- direct-region decode: 28.2241 ms
- total: 62.9041 ms -> 64.3878 ms
- 37,324,800 copied bytes/inter-frame avoided

Decision:
- **NO CPU PROMOTION**
- packed tile copies improve cache locality enough to beat the direct strided frame access.
- retain the concept for future GPU/direct-frame paths, where copy avoidance may have different economics.

## Next exact-speed target

Profile and optimize the remaining MC8R4 hot path:
1. pair-row / reduced-instruction SSE2 SAD evaluation;
2. SIMD residual generation and reconstruction;
3. full-pipeline 4K benchmark after each isolated promotion.
