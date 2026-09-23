# KHEPRI Stream Codec — Research Track v0

This branch is intentionally separate from AURORA/KEPHIR archive development.

## Frozen starting point

Validated baseline: **KEPHIR EXP-33H DIST-TOPO-AGGR**  
Commit: `5e655d5c587fba3ff8e15bc74b04fe3d43b77e3c`

Silesia validation:
- raw: 211,938,580 bytes
- compressed: 65,385,121 bytes
- ratio: 30.850976%
- compression: 26.7966 MB/s
- decompression: 124.207 MB/s
- SHA verification: all files passed

EXP-34 is not promoted into this branch: its first workflow failed during mode EXP34B_QUOTIENT decode, while EXP34A_ANCHORS was larger than EXP-33H on every tested Silesia file.

## Objective

Research a low-latency audio/video streaming codec that reuses KHEPRI's strongest parts as an entropy/predictive backend instead of attempting to recompress already-compressed MP4/AAC/H.264/AV1 bitstreams.

The project is experimental. Claims of superiority require reproducible benchmarks against appropriate codecs at matched quality, latency, resolution, frame rate and hardware.

## Architecture

```
raw media
  -> media parser
  -> reversible / controlled-loss preprocessing
  -> prediction
  -> residual mapping
  -> KHEPRI entropy backend
  -> independently decodable stream chunks
  -> transport packetization
```

### Audio path

Phase A is lossless PCM:
1. inter-channel decorrelation (reversible lifting / optional mid-side)
2. adaptive LPC/delta prediction
3. residual ZigZag mapping
4. residual-class modeling
5. KHEPRI entropy backend
6. independent audio blocks

Target block durations: 5, 10, 20 and 40 ms.

Later phases may add a perceptual lossy mode, but lossless and lossy results must never be mixed in comparisons.

### Video path

Phase A is lossless raw YUV:
1. plane separation
2. tile partitioning
3. spatial prediction
4. temporal prediction from bounded references
5. residual mapping
6. KHEPRI entropy backend
7. independently recoverable frame/tile groups

Early tests use YUV420p/8-bit, then 10-bit and 4:4:4.

A later lossy path may add transform + quantization + rate control. It will be treated as a separate codec profile.

## Streaming rules

- bounded memory
- no whole-file dependency
- deterministic decoder
- chunk-local recovery points
- explicit model reset/seed policy
- packet-loss damage bounded in time
- decode-first optimization
- no hidden dependence on future frames in low-latency mode
- timestamps and sequence numbers outside the entropy payload
- CRC per chunk during research builds

## First benchmark gates

A candidate is promoted only if all applicable gates pass:

1. bit-exact reconstruction for lossless profiles
2. chunk-by-chunk decode from a cold/reset state where required
3. no decoder state divergence after random chunk loss
4. measured encode/decode throughput
5. measured end-to-end algorithmic latency
6. compressed bytes / bitrate
7. peak memory
8. deterministic output across repeated runs

## Fair comparison set

Audio lossless: FLAC and other lossless references.  
Audio lossy/interactive: Opus-class references at matched perceptual conditions.  
Video lossless: FFV1 and lossless modes of relevant modern codecs.  
Video lossy: H.264/AVC, HEVC, VP9 and AV1 only under matched quality/latency settings.

General-purpose Silesia results remain useful for KHEPRI core research, but they are **not** evidence of audio/video codec performance.

## Research sequence

- KS-00: frozen EXP-33H baseline and chunk-overhead measurement
- KS-01: PCM residual front-end
- KS-02: adaptive audio predictor selection
- KS-03: persistent-vs-reset KHEPRI context experiments
- KS-04: raw YUV spatial predictor
- KS-05: bounded temporal video predictor
- KS-06: packet-loss / random-access experiments
- KS-07: real media corpus and codec comparison
- KS-08+: only after evidence, controlled-loss/perceptual modes
