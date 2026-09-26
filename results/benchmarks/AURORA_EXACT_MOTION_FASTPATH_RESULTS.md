# AURORA Exact Motion Fast Path Results

Date: 2026-09-26
GitHub Actions run: 36215128505
Status: PASS / PROMOTION CANDIDATE

## Change

MC8R4 now terminates the ordered candidate search when a candidate reaches SAD = 0.

This is an exact optimization:

- SAD is non-negative;
- zero is the global minimum;
- candidates are evaluated in the same deterministic order;
- the historical tie rule only replaces the winner on strictly lower cost;
- therefore the first zero-cost candidate is exactly the same winner selected by exhaustive search.

A compile-time switch,
`AURORA_DISABLE_EXACT_MOTION_FASTPATH`,
keeps the exhaustive reference path available for A/B validation.

## Correctness

Dedicated equivalence test:

`AURORA_EXACT_MOTION_FASTPATH_EQUIVALENCE_PASS`

Validated scenarios:
- identical structured frames;
- low-motion structured frames;
- deterministic random frames;
- 25-candidate full search;
- 9-candidate limited search;
- full lossless reconstruction.

A/B fingerprints were identical in every benchmark scenario.

Result:

**BITSTREAM_EQUIVALENCE = PASS**

## Performance

Native build:
`-O3 -march=native -mtune=native`

Tile geometry:
- 256 x 240
- YUV420p8
- 80 iterations per scenario

| Scenario | Exhaustive | Exact fast path | Speedup | Time reduction |
|---|---:|---:|---:|---:|
| Static | 0.143037 ms | 0.051539 ms | **2.775x** | **63.97%** |
| Low motion | 0.141972 ms | 0.088039 ms | **1.613x** | **37.99%** |
| Noise | 0.141045 ms | 0.142551 ms | 0.989x | -1.07% |

Output fingerprints, motion-map sizes and residual sizes were unchanged.

## Interpretation

The optimization is highly effective when perfect motion matches occur and effectively neutral
on incompressible/random motion input.

The small noise-case difference is within the range where additional repeated benchmarking is
appropriate, but there is no compression or correctness penalty.

## Decision

**PROMOTE to the AURORA Media research baseline.**

Reason:
- mathematically exact;
- deterministic;
- bitstream-stable in the validated cases;
- large benefit on static/low-motion content;
- no material regression on noise;
- tiny implementation complexity;
- reference A/B path remains available.

## Next exact-speed target

Do not immediately add approximate pruning to the production path.

Next preferred optimization:
**zero-copy/reference-view tile motion search**, removing current-frame and reference-frame
tile extraction/copy overhead while preserving the same MC8R4 decisions.
