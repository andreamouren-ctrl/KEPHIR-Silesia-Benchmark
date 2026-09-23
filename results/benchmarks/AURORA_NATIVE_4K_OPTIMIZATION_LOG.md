# AURORA Native 4K Optimization Log

Date: 2026-09-23

## Baseline smoke

Serial encode:
- ~2.26 fps

Serial decode:
- ~29.38 fps

## Tile parallelism

Run 35872312153.

Best point:
- 4 workers
- encode: ~6.40 fps
- decode: ~71.08 fps
- payload: 256,727 bytes

8 workers did not improve further on the GitHub runner.

## Exact SAD early-exit

Rejected.

The per-pixel branch prevented efficient vectorization and reduced throughput.

No byte-size change occurred.

## Motion shortlist

Run 35872941531.

Variants:
- exhaustive 25 candidates: 256,727 bytes
- shortlist 8: +5.61% payload, negligible speed gain
- shortlist 4: +5.59% payload, ~7.55% speed gain
- shortlist 2: +8.12% payload, ~6.31% speed gain

Decision:
- reject shortlist for Streaming4K;
- compression loss is far too large for the small speed benefit.

## Tile geometry

Run 35873202152.

- 256x240: baseline
- 384x240: +2.63% speed, +3.17% payload
- 512x480: -1.07% speed, -0.12% payload

Decision:
- keep 256x240 for Streaming4K;
- 512x480 may remain a MaxCompression research option.

## SSE2 exact SAD

Run 35873409304.

4-worker encode:
- before explicit SIMD: ~6.40 fps
- after SSE2 exact SAD: **~7.01 fps**

Payload:
- unchanged at **256,727 bytes**

Decision:
- PROMOTED.

The optimization preserves the exhaustive motion search and therefore does not intentionally alter motion-vector decisions or compression behavior.


## Native compiler tuning

Run 35873688674.

Same source and same payload, measured in the same workflow:

Baseline `-O3`, 4 workers:
- encode: 5.4036 fps
- decode: 49.9525 fps
- payload: 256,727 bytes

Native `-O3 -march=native -mtune=native`, 4 workers:
- encode: **5.9483 fps**
- decode: **50.3639 fps**
- payload: **256,727 bytes**

Encode improvement:
- approximately **+10.1%**

Decision:
- retain a portable baseline build;
- add/use a native-performance build profile on known target hardware;
- do not change the bitstream or codec decisions.
