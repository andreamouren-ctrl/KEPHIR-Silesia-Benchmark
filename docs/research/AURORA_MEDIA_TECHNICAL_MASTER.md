# AURORA Media / KHEPRI — Technical & Scientific Master Document

**Project:** AURORA Media  
**Compression engine:** KHEPRI  
**Repository branch:** `research/khepri-stream-codec`  
**Document role:** canonical technical/scientific reconstruction of the audio-video codec research and backend work  
**Status:** living engineering document  
**Date:** 2026-09-23

---

## 1. Purpose of this document

This file reconstructs, in one place, the full technical path followed to create the current AURORA Media / KHEPRI audio-video compression system.

It is intentionally more detailed than a README. It documents:

- the original engineering problem;
- the separation between the general-purpose KHEPRI compressor and the media codec;
- the scientific hypotheses that were tested;
- the reversible audio and video preprocessing stages;
- residual representation experiments;
- backend evolution from EXP-33H to EXP-37A and the role of EXP-44;
- all important KS and KSV checkpoints;
- negative results and rejected hypotheses;
- benchmark methodology;
- current lossless quality guarantees;
- the AURORA Media container;
- native muxing, demuxing, indexing, seek and streaming framing;
- the Python executable reference model;
- the C++20 backend;
- Python/C++ binary interoperability;
- the current dependency boundary;
- the distinction between standard techniques, project-owned implementation and candidate proprietary research;
- the exact state of the project and the next backend milestones.

This document is an engineering record. It is not a patentability opinion and does not claim that standard compression ideas are new merely because AURORA contains an independent implementation.

---

# PART I — PROJECT IDENTITY AND ARCHITECTURAL PRINCIPLES

## 2. Naming and product hierarchy

AURORA is the product and platform family.

KHEPRI is the compression technology / engine family beneath AURORA.

For the media project the naming model is:

```text
AURORA
├── AURORA Compressor
│   └── KHEPRI general-purpose engine
└── AURORA Media
    ├── AURORA Audio
    ├── AURORA Video
    ├── AURORA Container
    ├── AURORA Stream
    ├── AURORA Converter
    └── backend media session / decode pipeline
```

The active research backend is KHEPRI EXP-37A PREDICTIVE-DUAL-MATCH.

The research line remains separate from the stable AURORA Compressor application line. Experimental codec changes are not automatically part of the stable compressor product.

---

## 3. Fundamental development rules

The media project follows the following rules.

### 3.1 Lossless first

The first implementation target is mathematically lossless audio and video.

For every promoted lossless experiment:

```text
decoded bytes == original bytes
```

This is verified by SHA-256 comparisons, not visual inspection.

Therefore the current AURORA Audio and AURORA Video research paths do not lose quality.

A lossy/perceptual branch is a future and separate line of research.

### 3.2 Decode-first design

A transformation is not accepted merely because compression size improves.

The encoder and decoder must be deterministic and the complete roundtrip must be validated.

### 3.3 Bounded streaming state

The codec is designed around independent or bounded-state chunks rather than requiring the complete file.

This supports:

- local recovery;
- seek;
- progressive decoding;
- future network transport;
- bounded memory;
- deterministic resets.

### 3.4 Experimental checkpoints

Research is performed using small checkpoint sets, normally 3–5 variants per experiment.

The best valid variant is recorded immediately.

Large unstructured sweeps are avoided when a smaller experiment can answer the hypothesis.

### 3.5 No false novelty claims

Known techniques remain classified as background even when implemented independently.

AURORA may own its source code and binary format while using general engineering concepts that are not novel.

Candidate proprietary mechanisms require their own technical distinction and prior-art review.

---

# PART II — KHEPRI COMPRESSION BACKEND

## 4. KHEPRI background

KHEPRI originated as the compression engine used by AURORA Compressor.

Its research lineage includes:

- deterministic lossless compression;
- LZ-style match modeling;
- adaptive probability / residual modeling;
- arithmetic/range coding;
- deliberate distance-topology experiments;
- predictive processing;
- 3D/4D-inspired data structure experiments;
- floating-point / structured-data research in the wider compressor project.

For the media project, the important property is that KHEPRI is not treated as a black-box final codec.

Instead the media frontend deliberately transforms audio or video into a residual representation that KHEPRI can exploit.

The central research question became:

> Can media residuals be represented in a byte geometry that aligns with the statistical and match-distance behavior of the KHEPRI backend?

This led to KMRL and later video-specific routing experiments.

---

## 5. EXP-33H — distance-topology backend

EXP-33H became the initial stable backend used during the media research.

Validated Silesia state:

- raw corpus: 211,938,580 bytes;
- compressed: 65,385,121 bytes;
- ratio: approximately 30.850976%;
- compression speed: approximately 26.80 MB/s;
- decompression speed: approximately 124.21 MB/s;
- complete SHA verification: PASS.

Relevant configuration included:

- `K2_ADAPT_MODE=9`
- `K2_LAZY_MODE=1`
- `K2_PSG_MODE=3`
- `K2_DIST_TOPO_MODE=8`

The important research property of this backend was its deliberate sensitivity to relationships around line- and plane-scale distances, especially the 16 / 256 topology explored in EXP-33H.

This motivated residual geometries built around 256-position fields.

---

## 6. EXP-37A — current media backend

Later KHEPRI development produced EXP-37A PREDICTIVE-DUAL-MATCH.

The media branch imported and validated EXP-37A against EXP-33H.

On the KMRL FULL256 + TAIL16 real-audio stream:

- EXP-33H: 5,543,340 bytes;
- EXP-37A: 5,542,167 bytes;
- improvement: 1,173 bytes;
- approximately -0.02116%;
- roundtrip SHA: PASS.

The raw gain is small because the media frontend already performs substantial structure extraction before KHEPRI.

Nevertheless EXP-37A became the promoted backend because it improves final size without requiring the large search overhead of EXP-44.

Current media build configuration:

```text
K2_ADAPT_MODE=9
K2_LAZY_MODE=1
K2_PSG_MODE=3
K2_DIST_TOPO_MODE=8
K2_DUAL_MATCH_MODE=1
```

---

## 7. EXP-44 — structural router and why it is not the default media backend

EXP-44 is an important KHEPRI result and the best validated general-purpose structural-router line in the repository at the time of this document.

Validated Silesia result:

- compressed: 63,581,600 bytes;
- ratio: approximately 30.000012%;
- lossless SHA validation: PASS.

EXP-44 operates as a structural router over EXP-37A.

For each 512 KiB chunk it evaluates multiple reversible representations:

1. BASE;
2. delta-lag 4 followed by transpose width 4;
3. delta-lag 1024 followed by transpose width 1024.

The smallest final KHEPRI archive is selected.

This is effective for heterogeneous general data.

However, when EXP-44 was tested behind KMRL FULL256 + TAIL16 on real audio:

- all 16 chunks selected BASE;
- none selected the extra structural modes;
- EXP-44 output: 5,542,990 bytes;
- direct EXP-37A output: 5,542,167 bytes.

The media frontend had already performed structural transformation.

Running three backend candidates per chunk therefore duplicated work and increased encoding cost.

Decision:

- EXP-37A direct = active AURORA Media backend;
- EXP-44 = retained for general or unconditioned data;
- EXP-45 = research/oracle line and not promoted as a standalone media backend.

---

# PART III — AUDIO RESEARCH

## 8. Audio source model

The initial audio target is:

- PCM;
- signed 16-bit little-endian;
- stereo;
- 48 kHz;
- lossless.

The streaming research uses independently decodable blocks/chunks with reset boundaries.

Early candidate durations:

- 5 ms;
- 10 ms;
- 20 ms;
- 40 ms.

---

## 9. KS-01 — first reversible PCM frontend

KS-01 established that KHEPRI should not receive raw interleaved PCM directly.

The frontend used three standard reversible operations.

### 9.1 Reversible stereo decorrelation

Given left and right samples:

```text
side = left - right
mid  = right + (side >> 1)
```

Inverse:

```text
right = mid - (side >> 1)
left  = side + right
```

This is a lifting-style reversible stereo decorrelation.

It is explicitly treated as background technology, not a project invention.

### 9.2 First-order temporal delta

Within each independent block, samples are represented relative to the previous value.

Again this is standard predictive preprocessing.

### 9.3 ZigZag mapping

Signed residuals are mapped into unsigned integers so small positive and negative magnitudes remain numerically near zero.

This is also standard.

### 9.4 Temporary variable-byte representation

KS-01 used a simple byte-varint representation as an experimental frontend before the KHEPRI backend.

### 9.5 KS-01 result

Synthetic 12 s, 48 kHz stereo s16le:

- raw: 2,304,000 bytes;
- direct KHEPRI: approximately 2,304,114 bytes;
- best KS-01, 40 ms: 1,806,969 bytes;
- improvement versus direct KHEPRI: approximately 21.576%;
- all SHA checks: PASS.

Conclusion:

The frontend representation strongly affects KHEPRI media performance.

---

## 10. KMRL — KHEPRI Media Residual Lattice

KS-02 introduced the residual geometry research family.

Working name:

**KHEPRI Media Residual Lattice (KMRL)**.

The key idea was not simply “predict the audio.”

Instead:

1. produce reversible prediction residuals;
2. map signed residuals with ZigZag;
3. classify magnitudes;
4. reorganize residual bytes into structured fields;
5. align the physical representation with KHEPRI backend behavior.

### 10.1 Initial tile

Tile size:

```text
256 residual positions
```

This size was chosen to investigate coupling with the backend’s measured distance topology.

### 10.2 Predictor controls

Three reversible standard predictors were used as controls:

Mode 0:

```text
prediction = x[n-1]
```

Mode 1:

```text
prediction = 2*x[n-1] - x[n-2]
```

Mode 2:

```text
prediction = 3*x[n-1] - 3*x[n-2] + x[n-3]
```

These predictors are background techniques.

The research interest is not the predictor formulas themselves, but the interaction between predictor choice, residual representation and KHEPRI.

### 10.3 Residual magnitude classes

Initial KMRL residual magnitudes were divided conceptually into classes:

- class 0: < 16;
- class 1: < 256;
- class 2: < 65,536;
- class 3: < 2^32.

Class-specific bytes could then be serialized separately.

---

## 11. KS-02 — first KMRL result

Synthetic PCM result:

KS01 VARINT 20 ms:

- final archive: 1,810,900 bytes;
- 78.59809% of raw.

KMRL0 5 ms:

- 1,766,785 bytes;
- 76.68338%.

KMRL0 20 ms:

- 1,755,804 bytes;
- 76.20677%.

KMRL0 40 ms:

- 1,752,771 bytes;
- 76.07513%.

All outputs were bit-exact.

Important scientific observation:

The KMRL intermediate stream could be larger than the KS-01 intermediate stream while the final KHEPRI archive became smaller.

Therefore:

> minimizing frontend byte count is not the same objective as minimizing final KHEPRI archive size.

This became one of the core engineering lessons of the project.

---

## 12. KS-03 — real media audio

Synthetic data is insufficient to evaluate a codec.

KS-03 switched to real audio.

Source:

- Xiph Sintel trailer audio;
- converted to stereo PCM s16le 48 kHz;
- duration: 52 s;
- raw: 9,984,000 bytes;
- SHA-256:
  `146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744`.

Results:

### Direct KHEPRI EXP-33H

- 9,551,811 bytes;
- 95.67118% PCM;
- 15.3074 bits/sample.

### KS01 VARINT 20

- 6,999,614 bytes;
- 70.10831% PCM;
- 11.21733 bits/sample.

### KMRL0 20

- 5,775,307 bytes;
- 57.84562% PCM;
- 9.25530 bits/sample.

### FLAC reference

- 4,730,170 bytes in that checkpoint;
- 47.37750% PCM;
- 7.58040 bits/sample.

KMRL0 was:

- approximately 39.54% smaller than direct KHEPRI;
- approximately 17.49% smaller than KS01;
- still approximately 22.09% larger than FLAC.

This established KMRL as a meaningful media transform while also showing the remaining gap to mature lossless audio codecs.

---

## 13. KS-04 — FULL256 geometry

KS-04 tested multiple residual layouts.

### 13.1 CARRY_PACKED

A grouped field layout with predictor history carried through 256-position tiles inside the outer stream chunk.

Result:

- 5,757,954 bytes;
- approximately -0.30064% versus KMRL0.

### 13.2 FULL256

Residual bytes were transposed into fixed full 256-position byte planes.

For a residual requiring multiple bytes, byte significance planes were separated.

Result:

- frontend: 8,954,489 bytes;
- final KHEPRI: 5,552,105 bytes;
- 55.61003% PCM;
- 8.89760 bits/sample;
- -3.86493% versus KMRL0.

This result was significant because the intermediate representation became much larger while final compression became better.

Again, the data supported a backend-coupling interpretation rather than simple precompression.

### 13.3 CLASS_FULL256

A dedicated explicit 256-byte residual-class plane was added.

Result:

- frontend: 14,279,289 bytes;
- final: 6,478,016 bytes;
- major regression.

Decision:

CLASS_FULL256 rejected.

FULL256 promoted.

---

## 14. KS-05 — topology-aware predictor heuristic

A first attempt was made to choose predictors based on a simplified proxy for KHEPRI recurrence around distances 16 and 256.

Policies included:

- class-cost baseline;
- physical plane size;
- topology hit heuristic.

Results:

- class baseline: 5,552,224 bytes;
- physical-plane bytes: 5,551,627 bytes;
- topology 16/256 heuristic: 5,573,597 bytes.

The topology heuristic regressed approximately 0.385%.

Decision:

Rejected.

Scientific lesson:

A count of equal bytes at selected offsets is too weak a proxy for the real cost function of the complete KHEPRI backend.

This negative result is important and remains documented.

---

## 15. KS-06 — topology-preserving sparsity

FULL256 contains padding.

KS-06 tested whether some padding could be removed without destroying useful geometry.

Variants:

1. FULL256 baseline;
2. TAIL16;
3. MASK16.

### TAIL16

Each plane keeps data through the last non-zero 16-byte group.

Result:

- frontend: 7,869,535 bytes;
- final: 5,543,348 bytes;
- 55.5223% PCM;
- -0.1577% versus FULL256.

### MASK16

A 16-group occupancy mask allowed zero 16-byte groups to be omitted.

Result:

- frontend: 7,456,965 bytes;
- final: 5,544,324 bytes;
- -0.1401% versus FULL256.

Even though MASK16 had the smaller frontend representation, TAIL16 produced the smaller final KHEPRI archive.

Decision:

TAIL16 promoted as the active serialization refinement.

Again:

```text
smallest frontend != smallest final KHEPRI archive
```

---

## 16. KS-07 — migration to newer KHEPRI backend

KS-07 investigated moving the media codec from EXP-33H to the newer KHEPRI line.

EXP-44 structural routing selected BASE on all media chunks, proving its extra transforms were redundant behind the specialized media frontend.

KS-07B therefore compared direct EXP-37A to EXP-33H.

Result:

- EXP-33H: 5,543,340 bytes;
- EXP-37A: 5,542,167 bytes;
- SHA: PASS.

EXP-37A became the audio/video backend baseline.

---

# PART IV — VIDEO RESEARCH

## 17. Initial video target

The first video research profile is:

- YUV420p;
- 8-bit;
- lossless;
- independent frame/GOP groups;
- bounded reference state;
- deterministic decoder.

The objective is not to copy H.264/HEVC/AV1 structures.

Standard spatial or temporal prediction and motion compensation may be used as controls, but project-specific research must add something materially distinct.

---

## 18. Spatial and temporal baseline

The early video frontend separated:

- Y plane;
- U plane;
- V plane.

Spatial prediction and previous-frame temporal residuals were tested.

The low-motion Akiyo sequence demonstrated that simple reversible temporal prediction can create data KHEPRI compresses effectively.

This became the TEMP control path.

---

## 19. Motion compensation baseline

Medium/high-motion sequences exposed the weakness of previous-frame-only prediction.

A bounded integer-pixel block motion compensation implementation was therefore built as a control.

Current MC8R4 configuration:

- block size: 8x8 luma;
- search radius: 4;
- integer-pixel displacement;
- chroma motion derived consistently for YUV420;
- residual stored reversibly;
- motion map stored as side information.

This is explicitly BACKGROUND technology.

The implementation code is project-owned, but generic motion compensation itself is not treated as a project invention.

---

## 20. KSV-04 — block-major residual lattice negative result

A hypothesis was tested:

> If a 16x16 luma residual block occupies one contiguous 256-byte region, KHEPRI’s 256-scale topology may exploit it better.

Results:

Foreman MC16/R4:

- raster: 5,828,903;
- lattice: 5,862,820;
- +0.582% regression.

Foreman MC8/R4:

- raster: 5,781,687;
- lattice: 5,801,733;
- +0.347%.

Bus MC16/R4:

- raster: 1,865,101;
- lattice: 1,872,772;
- +0.411%.

Bus MC8/R4:

- raster: 1,842,551;
- lattice: 1,847,176;
- +0.251%.

Decision:

Fixed block-major serialization rejected.

This prevented the project from incorrectly assuming that geometric alignment alone guarantees backend benefit.

---

## 21. Major codec benchmark

A common benchmark compared AURORA/KHEPRI against major lossless codecs.

### 21.1 Audio

Source:

- 52 s stereo PCM 48 kHz;
- 9,984,000 raw bytes.

Results:

| Codec | Bytes | % PCM |
|---|---:|---:|
| WavPack high compression | 4,587,265 | 45.946% |
| FLAC level 8 | 4,663,310 | 46.708% |
| ALAC | 4,862,860 | 48.707% |
| AURORA/KHEPRI | 5,542,173 | 55.511% |

AURORA remained behind mature lossless audio codecs in compression ratio.

### 21.2 Video — Akiyo low motion

Raw: 11,404,800 bytes.

Results:

- HEVC lossless: 1,548,805;
- H.264 lossless: 1,550,700;
- AV1 lossless: 1,664,745;
- VP9 lossless: 1,697,847;
- AURORA TEMP + EXP37A: 2,208,653;
- FFV1: 3,468,622.

AURORA TEMP beat FFV1 strongly on this low-motion clip but remained behind the modern predictive video codecs.

### 21.3 Foreman medium motion

- HEVC lossless: 3,722,889;
- AV1 lossless: 3,790,903;
- VP9 lossless: 3,809,998;
- H.264 lossless: 3,893,089;
- FFV1: 5,295,415;
- AURORA MC8R4: 5,779,455;
- AURORA TEMP: 6,076,824.

Motion representation was clearly the main weakness.

### 21.4 Bus high motion

- HEVC lossless: 1,269,735;
- VP9 lossless: 1,272,775;
- H.264 lossless: 1,311,224;
- AV1 lossless: 1,336,862;
- FFV1: 1,593,314;
- AURORA MC8R4: 1,841,866;
- AURORA TEMP: 2,008,806.

Again, motion handling dominated the gap.

---

## 22. KSV-05 — adaptive routing

The next engineering goal was to eliminate manual per-clip selection between TEMP and MC8R4.

A router was created that:

1. divides the stream into bounded routing windows;
2. encodes each candidate mode;
3. sends each result through KHEPRI EXP-37A;
4. selects the mode producing the smaller final payload;
5. stores the selected mode in a deterministic stream.

Generic mode selection by compressed size is considered background engineering.

The value of this experiment was architectural: AURORA could now choose internally rather than depending on external/manual classification.

---

## 23. Routing horizon experiment

Routing horizons tested:

- 10 frames;
- 20 frames;
- 30 frames;
- 50 frames.

Aggregate results across Akiyo, Foreman and Bus:

- 10 frames: 9,848,450 bytes;
- 20 frames: 9,784,828 bytes;
- 30 frames: 9,815,461 bytes;
- 50 frames: 9,806,600 bytes.

20 frames won.

Prior manually selected AURORA aggregate:

- 9,829,974 bytes.

FFV1 aggregate:

- 10,357,351 bytes.

20-frame automatic routing therefore achieved:

- 45,146 fewer bytes than the prior manually selected AURORA aggregate;
- approximately -0.459%;
- 572,523 fewer bytes than FFV1 aggregate on this three-clip research corpus;
- approximately -5.528%.

Important limitation:

This does not prove general superiority over FFV1.

The corpus is small and must be expanded substantially.

---

## 24. KASH hypothesis

The routing-horizon result suggested that KHEPRI state/reset duration itself influences final compression.

This motivated a future research direction:

**KASH — KHEPRI Adaptive State Horizon**.

Research question:

> Can reset/state horizon be selected using KHEPRI-specific residual-state behavior rather than a fixed frame count?

This remains a hypothesis.

Generic adaptive chunking is not claimed as an invention.

---

# PART V — QUALITY AND LOSSLESS GUARANTEE

## 25. Current quality behavior

The active codec path is lossless.

Audio decode reconstructs the exact original PCM.

Video decode reconstructs the exact original YUV420p bytes.

Therefore:

- no visual detail is intentionally discarded;
- no audio samples are intentionally approximated;
- no generational degradation occurs after a valid encode/decode cycle;
- PSNR for the lossless path is conceptually infinite where compared byte-for-byte;
- SHA-256 is the decisive validation mechanism.

Lossy benchmark references such as Opus/AAC/H.264/HEVC/VP9/AV1 at fixed bitrate are tracked separately and are not ranked directly against the current AURORA lossless mode.

---

# PART VI — AURORA MEDIA CONTAINER

## 26. Why a native container was created

The project should not depend on FFmpeg/libavformat to read its own format.

Therefore AURORA Media v0.1 introduced a project-owned binary container implementation.

Working extension:

```text
.aum
```

The extension is still considered a research baseline and can change before a public format freeze.

---

## 27. Container design goals

The v0.1 format provides:

- deterministic binary representation;
- versioning;
- multiple tracks;
- audio/video track metadata;
- timestamped packets;
- packet durations;
- key/recovery flags;
- per-packet integrity;
- final random-access index;
- index integrity;
- footer-based index discovery;
- recovery-point seek.

The format is little-endian.

---

## 28. Main binary structures

### File header

Magic:

```text
AUM1
```

Contains:

- magic;
- version;
- flags;
- track count;
- timescale;
- reserved field.

Current default timescale:

```text
1,000,000 units/second
```

which corresponds naturally to microsecond timestamps.

### Track header

Each track stores:

- track id;
- track type;
- codec id;
- flags;
- four generic parameter fields.

Current audio mapping uses the parameters for values such as:

- sample rate;
- channel count;
- bit depth;
- packet sample count.

Current video mapping uses:

- width;
- height;
- FPS numerator;
- FPS denominator.

### Packet header

Each packet stores:

- track id;
- flags;
- PTS;
- duration;
- payload size;
- CRC32;
- reserved fields.

### Index

The final index stores:

- track id;
- flags;
- PTS;
- duration;
- packet file offset;
- packet payload size.

### Footer

Magic:

```text
AUF1
```

The footer locates the index and stores its CRC.

---

## 29. Recovery model

Current AURORA Media packetization intentionally makes codec packets independently decodable.

Audio packets are marked as recovery packets.

Video media packets can be marked KEY + RECOVERY.

This gives the container a local recovery model appropriate for:

- seeking;
- progressive decode;
- future streaming;
- bounded damage after corruption or packet loss.

---

# PART VII — AURORA STREAM PROTOCOL

## 30. Stream framing

AURORA Stream v0.1 defines framing independent of a specific transport.

Magic:

```text
AUS1
```

A stream packet contains:

- format version;
- track id;
- flags;
- sequence number;
- PTS;
- duration;
- payload size;
- CRC;
- payload.

The protocol is not itself TCP or UDP.

It can later be carried by an ordered transport or adapted to a datagram transport.

---

## 31. Ordered receiver

The receiver tracks the next expected sequence number.

A sequence discontinuity is detected explicitly.

The C++20 backend additionally contains an incremental byte-stream parser capable of accepting arbitrary partial input fragments and emitting a packet only after the complete frame is available.

---

# PART VIII — FIRST COMPLETE END-TO-END MEDIA STACK

## 32. AURORA Media v0.1 pipeline

The first complete validated path is:

```text
PCM s16le + YUV420p8
        ↓
AURORA audio/video packet encoders
        ↓
KHEPRI EXP-37A
        ↓
AURORA muxer
        ↓
AUM container
        ↓
AURORA demuxer
        ↓
AURORA packet decoders
        ↓
media session / player core
        ↓
original PCM + original YUV
```

External multimedia libraries are not needed to create or read the native AUM format when canonical raw inputs are already available.

---

## 33. End-to-end validation

GitHub Actions run:

```text
35837750505
```

Result:

```text
PASS
```

Synthetic source media was generated without FFmpeg.

Container:

- 17,716 bytes;
- 2 tracks;
- 7 packets;
- 5 audio packets;
- 2 video packets.

Decoded audio:

- 192,000 bytes.

Decoded video:

- 1,520,640 bytes.

Audio source and decoded SHA-256:

```text
bd7bfce6da2105c980706adba20fc19ef746579587255237d2ff19f11b449d02
```

Video source and decoded SHA-256:

```text
ccd417b50327127c6d0569a6676d265fd4fb7d5660100a5f808a50caa3a7380a
```

Both matched exactly.

Corruption tests:

- container payload corruption rejected: PASS;
- stream packet corruption rejected: PASS.

---

# PART IX — PYTHON REFERENCE MODEL

## 34. Purpose

Python remains the executable reference implementation for the binary format and codec orchestration.

It is not intended to be the final performance implementation.

Its purposes are:

- fast experimentation;
- specification validation;
- regression tests;
- exact binary reference;
- C++ interoperability checking;
- scientific reproducibility.

Canonical location:

```text
src/python/reference/
```

---

# PART X — C++20 BACKEND

## 35. Motivation

A production codec backend needs:

- predictable performance;
- bounded allocations;
- integration with AURORA applications;
- deterministic binary parsing;
- streaming APIs;
- multithreading;
- robust error handling.

Therefore the stable backend is being migrated to C++20 while Python remains the reference.

---

## 36. C++20 container implementation

Canonical location:

```text
src/cpp/aurora_media/
```

Current modules include:

### AuroraMediaContainer

Implements:

- AUM header writing;
- track serialization;
- packet serialization;
- CRC32;
- index construction;
- footer writing;
- AUM parsing;
- index bounds validation;
- packet/index consistency validation;
- packet CRC verification;
- recovery-point seek.

### AuroraStreamProtocol

Implements:

- AUS1 serialization;
- AUS1 decode;
- CRC verification;
- ordered sequence receiver;
- incremental byte parser.

### AuroraMediaSession

Implements:

- track validation;
- audio/video track discovery;
- PTS timeline construction;
- sequential packet iteration;
- cursor/reset;
- recovery-point seek.

No GUI belongs in these modules.

---

## 37. Binary interoperability

The Python and C++ implementations were tested in both directions.

Python writer → C++ reader:

```text
PASS
```

C++ writer → Python reader:

```text
PASS
```

C++ writer → C++ reader:

```text
PASS
```

Streaming incremental C++ parser:

```text
PASS
```

C++ stream CRC rejection:

```text
PASS
```

Media-session timeline / seek:

```text
PASS
```

Validation run:

```text
35839731226
```

C++ quality gate:

```text
-O2 -std=c++20 -Wall -Wextra -Werror
```

This establishes AUM v0.1 as a binary compatibility baseline shared by two independently implemented readers/writers.

---

# PART XI — DEPENDENCY BOUNDARY

## 38. What is native AURORA code

Current project-owned implementation includes:

- KHEPRI compression engine;
- media residual research code;
- audio frontend implementation;
- video frontend implementation;
- AUM container;
- muxer;
- demuxer;
- packet framing;
- timestamps/interleave;
- index;
- seek;
- CRC integration;
- stream framing;
- ordered stream receiver;
- incremental stream parser;
- media session;
- codec bridge;
- converter from canonical raw inputs;
- headless decode orchestration.

---

## 39. What external tools are still used for

External tools such as FFmpeg are used in research/benchmark workflows for:

- decoding existing public test media into canonical raw PCM/YUV;
- encoding reference codecs;
- comparing against FLAC/ALAC/WavPack;
- comparing against FFV1/H.264/HEVC/VP9/AV1;
- computing reference metrics in lossy benchmark experiments.

They are not required for AURORA to parse its own AUM container.

The long-term arbitrary-format converter may use external import adapters at the boundary:

```text
external format -> adapter decode -> canonical PCM/YUV -> AURORA core
```

This does not make the external codec part of AURORA’s own format.

---

# PART XII — STANDARD TECHNIQUES VS PROJECT RESEARCH

## 40. Explicit background techniques

The project does not claim novelty for:

- linear prediction;
- finite differences;
- reversible stereo decorrelation;
- ZigZag signed mapping;
- generic residual entropy coding;
- generic bit planes;
- fixed byte-plane transposition;
- generic raster reordering;
- spatial video prediction;
- temporal prediction;
- integer/fractional motion compensation as a general concept;
- motion-vector prediction;
- selecting a mode by estimated rate;
- generic transforms/quantization;
- muxing;
- timestamps;
- CRC;
- indexing;
- seeking;
- generic adaptive segmentation.

These techniques may still be independently implemented in AURORA source code.

---

## 41. Candidate project-specific research

Historical/current candidate research families include:

### KMRL

KHEPRI Media Residual Lattice.

Research interest:

coupling a reversible media residual field with a serialization geometry deliberately matched to the behavior of the KHEPRI backend.

### KTARP

Topology-adaptive residual permutation.

The tested KS-05 form regressed and was rejected.

Status:

```text
REJECTED-IP / NOT PROMOTED IN CURRENT FORM
```

### KASH

KHEPRI Adaptive State Horizon.

Current status:

```text
RESEARCH HYPOTHESIS
```

Its purpose is to investigate whether KHEPRI-specific state behavior can drive recovery/reset horizon.

No patentability conclusion has been made.

---

# PART XIII — NEGATIVE RESULTS THAT MUST NOT BE LOST

## 42. Why negative experiments are preserved

Compression research can easily repeat failed ideas if only winning results are documented.

The repository therefore preserves negative results such as:

- explicit class plane in FULL256: regression;
- simple 16/256 recurrence predictor heuristic: regression;
- fixed block-major video lattice: regression;
- EXP-44 structural routing behind already-conditioned KMRL: redundant;
- smaller frontend stream does not always mean smaller final KHEPRI archive.

These findings actively constrain future development.

---

# PART XIV — BENCHMARK METHODOLOGY

## 43. Lossless acceptance criteria

A valid lossless result requires:

1. source fixed and identified;
2. encoder completes;
3. decoder completes;
4. output size matches where appropriate;
5. SHA-256 of reconstructed raw media equals original;
6. final archive size recorded;
7. throughput recorded when meaningful;
8. experiment configuration recorded.

A compression result without roundtrip verification is not promoted.

---

## 44. Fair comparison principles

Audio lossless is compared to lossless audio codecs.

Video lossless is compared to lossless video configurations.

Lossy reference codecs are measured separately.

Lossless and lossy byte counts are never placed into one “winner” ranking without quality matching.

For future lossy AURORA work, evaluation should include:

- bitrate;
- PSNR;
- SSIM;
- VMAF;
- encode latency;
- decode latency;
- memory;
- recovery behavior.

For audio lossy work, perceptual evaluation must accompany bitrate comparison.

---

# PART XV — CURRENT REPOSITORY STRUCTURE

## 45. Canonical layout

The repository is being normalized into:

```text
/
├── README.md
├── docs/
│   ├── architecture/
│   ├── backend/
│   ├── benchmarks/
│   ├── ip/
│   ├── research/
│   ├── roadmap/
│   └── specs/
├── src/
│   ├── cpp/
│   │   └── aurora_media/
│   └── python/
│       └── reference/
├── tests/
│   ├── cpp/
│   └── python/
├── research/
│   ├── audio/
│   ├── video/
│   └── backend/
├── benchmarks/
│   └── major_codecs/
├── results/
│   ├── audio/
│   ├── video/
│   └── benchmarks/
├── source_parts/
└── .github/workflows/
```

The historical `streaming/` tree remains temporarily for compatibility and reproducibility until every workflow/import is migrated.

---

# PART XVI — CURRENT STATUS

## 46. What works today

### General KHEPRI

- stable validated research backend lineage;
- EXP-37A active for media;
- EXP-44 retained as general structural router research.

### Audio

- lossless PCM;
- stereo reversible decorrelation;
- prediction residuals;
- KMRL;
- FULL256;
- TAIL16;
- EXP-37A backend;
- bit-exact reconstruction.

### Video

- lossless YUV420p8;
- spatial/temporal reversible path;
- bounded motion-compensated control path;
- adaptive routing;
- 20-frame routing horizon baseline;
- bit-exact reconstruction.

### Container/backend

- AUM v0.1;
- native mux/demux;
- PTS/duration;
- index;
- seek;
- CRC;
- recovery flags;
- AUS1 streaming framing;
- ordered receiver;
- incremental parser;
- Python reference;
- C++20 container/session/stream backend;
- binary Python/C++ interoperability.

---

## 47. What is not finished

The following are not yet production-complete:

- native C++20 audio codec bridge;
- native C++20 video codec bridge;
- in-process KHEPRI API replacing research subprocess invocation;
- production packet scheduler;
- multithreaded codec pipeline;
- fuzzing campaign;
- hard parser resource limits;
- network socket layer;
- congestion/loss recovery strategy;
- finalized public container extension/specification;
- large real-world media corpus validation;
- 10-bit / 12-bit video;
- HDR metadata;
- multichannel audio;
- subtitles;
- chapters;
- metadata tags;
- encryption;
- lossy/perceptual AURORA profile.

GUI work is intentionally outside the current backend scope.

---

# PART XVII — NEXT BACKEND MILESTONES

## 48. Immediate order of work

### Milestone B03 — Codec interfaces

Define C++20 interfaces for:

- audio packet encoder;
- audio packet decoder;
- video packet encoder;
- video packet decoder;
- KHEPRI backend interface;
- error/status model;
- configuration structs.

### Milestone B04 — KHEPRI in-process adapter

Remove filesystem/subprocess dependence from production codec execution.

Goal:

```text
memory buffer -> KHEPRI encode -> memory buffer
memory buffer -> KHEPRI decode -> memory buffer
```

### Milestone B05 — Native audio path

Port the promoted audio path to C++20 while comparing every encoded/decoded stage to the Python reference.

### Milestone B06 — Native video path

Port TEMP / MC8R4 routing and future research modes to C++20.

### Milestone B07 — Non-seekable mux/demux

Support live stream creation where a final index may not exist yet.

### Milestone B08 — Robustness

Add:

- malformed header tests;
- oversized field rejection;
- malicious index bounds tests;
- CRC faults;
- truncation tests;
- random corruption;
- fuzzing.

### Milestone B09 — Scheduler

Parallelize independent packet encode/decode while preserving deterministic output order.

---

# PART XVIII — FINAL ENGINEERING PRINCIPLE

## 49. Core design statement

AURORA Media is not being developed as “KHEPRI applied blindly to video.”

The architecture is:

```text
media structure
      ↓
reversible prediction
      ↓
residual field
      ↓
AURORA/KHEPRI-specific representation
      ↓
KHEPRI backend
      ↓
independent recoverable packets
      ↓
native AURORA container / stream
```

The long-term research value lies in the interaction between these stages.

The project must continue to measure the final compressed output, preserve negative experiments, maintain lossless verification, and keep standard methods clearly separated from candidate project-specific innovations.

---

## 50. Canonical baselines at the date of this document

### Audio baseline

```text
PCM s16le stereo
→ reversible stereo decorrelation
→ predictor residuals
→ ZigZag
→ KMRL FULL256
→ TAIL16
→ KHEPRI EXP-37A
```

### Video baseline

```text
YUV420p8
→ bounded independent windows
→ TEMP or MC8R4 reversible prediction
→ automatic final-KHEPRI-size routing
→ 20-frame routing horizon
→ KHEPRI EXP-37A
```

### Media backend baseline

```text
AUM v0.1 container
AUS1 stream framing
Python executable reference
C++20 native container/session/stream backend
Python ↔ C++ binary compatibility validated
```

These are the reference points from which subsequent AURORA Media backend development must proceed.
