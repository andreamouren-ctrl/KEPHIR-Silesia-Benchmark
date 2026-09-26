# AURORA Media Natural Video Corpus v1 Results

Date: 2026-09-26
GitHub Actions run: 36228719982
Status: PASS

## Scope

Real-content, compression-first lossless benchmark using uncompressed Xiph YUV4MPEG sources.

Validation set:
- container — low motion
- coastguard — camera motion
- mobile — texture/pan
- football — high motion
- stefan — human/camera motion

Each source:
- first 60 frames;
- raw YUV420p;
- final file size includes AUM/MKV/container overhead;
- every available decoded output SHA-256 verified against the exact raw input.

Aggregate raw input:
- **44,098,560 bytes**

Timing is diagnostic only. The current AURORA full-stack reference path still includes
Python/subprocess orchestration, so this checkpoint is used primarily for compression behavior.

## Aggregate

| Codec | Bytes | Ratio to raw |
|---|---:|---:|
| AV1 lossless | 18,279,836 | 41.452% |
| VP9 lossless | 18,705,614 | 42.418% |
| HEVC lossless | 18,802,467 | 42.637% |
| H.264 lossless | 18,943,463 | 42.957% |
| FFV1 | 21,939,299 | 49.751% |
| **AURORA Media** | **24,821,317** | **56.286%** |

AURORA aggregate delta:
- vs FFV1: **+13.136% larger**
- vs H.264 lossless: **+31.028% larger**
- vs HEVC lossless: **+32.011% larger**
- vs VP9 lossless: **+32.694% larger**
- vs AV1 lossless: **+35.785% larger**

## Per-source

### container — low motion

- AURORA: **3,616,085 B / 39.633%**
- FFV1: 3,890,960 B / 42.646%
- HEVC lossless: 2,777,770 B / 30.445%

AURORA is **7.064% smaller than FFV1** on this source.

This confirms that the current AURORA temporal/residual architecture can be competitive
with a mature archival codec when motion is predictable.

### coastguard — camera motion

- AURORA: **4,888,376 B / 53.578%**
- FFV1: 4,522,297 B / 49.566%
- AV1 lossless: 3,814,202 B / 41.805%

AURORA is **8.095% larger than FFV1**.

### mobile — texture/pan

- AURORA: **6,030,434 B / 66.095%**
- FFV1: 5,518,245 B / 60.482%
- HEVC lossless: 4,095,671 B / 44.890%

AURORA is **9.282% larger than FFV1**.

### football — high motion

- AURORA: **5,889,029 B / 64.546%**
- FFV1: 4,157,819 B / 45.571%
- AV1 lossless: 4,125,710 B / 45.219%

AURORA is **41.637% larger than FFV1**.

This is the clearest failure mode in the current corpus.

### stefan — human/camera motion

- AURORA: **4,397,393 B / 57.836%**
- FFV1: 3,849,978 B / 50.636%
- AV1 lossless: 3,424,489 B / 45.040%

AURORA is **14.219% larger than FFV1**.

## Engineering conclusion

The current natural-content bottleneck is **video prediction quality**, not container overhead
and not lossless correctness.

The result pattern is highly diagnostic:

- low motion: current temporal architecture is already useful;
- camera motion: current ±4-pixel MC field is insufficient;
- texture/pan: residual entropy remains too high;
- high motion: current MC8R4 model fails badly;
- human/camera motion: improvement is required before AURORA can compete broadly.

The next compression R&D target is therefore not another KHEPRI speed micro-optimization.

## Next experiment

**KSV-13 Natural Motion Radius Sweep**

Measure on the same natural corpus:
- current MC8R4;
- MC8R6;
- TEMP fallback;
- final KHEPRI/AUM payload impact;
- per-source mode decisions;
- encode-cost increase.

If a modest larger radius materially improves football/coastguard/mobile, promote the idea
into a hierarchical or adaptive wide-motion search rather than globally paying the full
candidate-count cost.
