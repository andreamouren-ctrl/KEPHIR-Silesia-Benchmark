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


---

# PART XIX — GENERAL-PURPOSE KHEPRI EVOLUTION RELEVANT TO AURORA MEDIA

## 51. Why the general-purpose line matters to the media codec

AURORA Media and the general-purpose KHEPRI compressor are separate development lines, but they share the same backend technology family.

The separation is deliberate:

- AURORA Compressor can continue to use a stable production core;
- KHEPRI research can evolve aggressively without destabilizing the application;
- AURORA Media can select a validated KHEPRI checkpoint as its backend;
- a new experimental KHEPRI result is never automatically promoted into the media codec.

The media branch therefore records the general-purpose lineage only where it affects backend selection, residual representation, throughput, or bitstream design.

## 52. EXP-22 baseline

EXP-22 established a reproducible post-R3 baseline with:

- long LZ matches;
- chunked parallel encoding;
- sampled multidimensional prediction;
- adaptive probability models;
- arithmetic/range coding;
- distance caches;
- deterministic lossless decode.

On the 211,938,580-byte Silesia corpus:

- compressed size: 70,974,062 bytes;
- ratio: 33.4880332%;
- compression throughput: approximately 32.14 MB/s in the original benchmark;
- decompression throughput: approximately 104.61 MB/s;
- SHA verification: PASS.

This checkpoint also exposed important container-level issues that are independent of the compression core:

- raw chunks needed stronger integrity protection;
- path traversal had to be rejected;
- empty directories required explicit representation;
- permissions/timestamps were not yet preserved.

These findings belong to container engineering and must not be confused with entropy-coding correctness.

## 53. EXP-23 — distance-penalty recalibration

The parser match cost used the form:

```text
match_cost = MC
           + length_term
           + DPEN * log2(distance + 1)
```

with a length term approximately:

```text
1.0                         if length <= 7
log2(length + 1)            otherwise
```

A sweep showed that the earlier distance penalty was too strong.

Promoted parameters:

```text
LIT  = 6.55
MC   = 9.42
DPEN = 1.20
```

Full Silesia:

- 66,112,603 bytes;
- 31.1942276%;
- SHA PASS.

This was a large structural improvement because the parser stopped rejecting useful longer-distance matches too aggressively.

## 54. EXP-24 through EXP-27 — adaptive parser tuning

### EXP-24

The distance penalty became chunk-content aware.

The best discrete policy classified chunks using printable-text fraction rather than a continuous formula.

Result:

- 65,718,527 bytes;
- 31.0082888%;
- SHA PASS.

### EXP-25

Continuous adaptive distance penalties were tested.

They regressed against the discrete bands.

Decision:

```text
REJECTED
```

Lesson:

A smooth formula was not automatically superior to discrete content classes.

### EXP-26

Band thresholds and penalties were tuned further.

Best checkpoint:

- 65,633,259 bytes;
- 30.9680564%;
- SHA PASS.

### EXP-27

Lazy matching depth became adaptive.

Best EXP-27A:

- 65,584,515 bytes;
- 30.9450573%;
- SHA PASS.

This checkpoint later became an important base for prediction-aware parser work.

## 55. EXP-28 and EXP-29

EXP-28 attempted token/distance coupling by splitting models according to match properties.

The best valid variant regressed.

Decision:

```text
REJECTED
```

Reason:

The additional conditioning fragmented statistics more than it improved specialization.

EXP-29 produced only a small refinement and was superseded by the later predictive parser line.

## 56. EXP-30 — Predictive Opportunity Cost

This was one of the most important architectural changes.

The parser stopped evaluating a match only as a generic LZ token.

Instead, it estimated how expensive the literal/residual sequence would be under KHEPRI's predictor and compared that against the match cost.

Conceptually:

```text
literal_gain(position, length)
    = predicted_literal_cost(position, length)
      - encoded_match_cost(length, distance)
```

A match therefore becomes more valuable when it replaces a sequence that the residual model considers expensive.

EXP-30A:

- 65,393,000 bytes;
- 30.85469%;
- compression approximately 30.93 MB/s in validation;
- decompression approximately 124.43 MB/s;
- SHA PASS.

This is a key point in the evolution of KHEPRI: LZ parsing and multidimensional prediction stopped being independent subsystems.

## 57. EXP-31 — Predictive Surprise Gating

The literal cost was separated into low-, medium-, and high-surprise zones.

High-surprise residual regions gave stronger incentive to matches, while predictable regions required less aggressive substitution.

Best EXP-31C:

- 65,386,865 bytes;
- 30.8517991%;
- SHA PASS.

The size gain over EXP-30A was small and encoding speed regressed, so this checkpoint was useful mainly as a research reference.

## 58. EXP-32 — sparse predictor opportunity field

EXP-32 sampled predictive opportunity cost instead of evaluating the full expensive field at every position.

The useful compromise was EXP-32A stride-2:

- 65,394,019 bytes;
- 30.8551746%;
- compression approximately 30.18 MB/s;
- decompression approximately 118.48 MB/s;
- SHA PASS.

This became a balanced checkpoint because it retained almost all compression while reducing predictor overhead.

## 59. EXP-33H — distance topology

Distance topology bonuses were introduced into parser cost without changing the bitstream representation.

The promoted mode favored distances close to the internal 16/256 geometry:

- 15/16/17;
- 255/256/257;
- selected multiples of 16 and 256.

EXP-33H result:

- 65,385,121 bytes;
- 30.8509763%;
- compression approximately 26.80 MB/s;
- decompression approximately 124.21 MB/s;
- SHA PASS.

The key distinction is that the topology modifies encoder choice only. It does not require a decoder side channel.

## 60. EXP-34, EXP-35 and EXP-36 — rejected direct transforms/models

### EXP-34

Direct distance-symbol transforms attempted to encode lattice anchors and distance quotients explicitly.

All valid variants regressed.

Lesson:

An encoder-side topology preference can help even when explicit topology syntax does not.

### EXP-35

Distance deltas relative to previous matches were tested with an explicit gate.

All variants regressed strongly.

Lesson:

The existing distance representation was already efficient enough that extra signaling cost dominated.

### EXP-36

A 16-way spatial residual expert indexed by data position was added.

All tested variants regressed.

Lesson:

Position-conditioned residual models can fragment statistics when the position class is not strongly predictive.

## 61. EXP-37 — Predictive Dual Match

EXP-37 introduced a second match candidate selected using the predicted cost of the literals it would replace.

The match finder therefore considered two different notions of quality:

1. conventional LZ match quality;
2. prediction-aware opportunity value.

EXP-37A:

- 65,308,450 bytes;
- 30.81480%;
- compression approximately 18.81 MB/s in validation;
- decompression approximately 127.74 MB/s;
- SHA PASS.

This became the strongest direct non-router Max checkpoint and the active KHEPRI backend selected for AURORA Media.

## 62. EXP-38 and EXP-39 — fused predictive matching

The first EXP-37 implementation rescanned the hash chain to find the predictive candidate.

EXP-38 fused conventional and predictive candidate collection into one traversal.

EXP-38A:

- 65,324,447 bytes;
- 30.82235%;
- compression approximately 22.01 MB/s;
- decompression approximately 121.56 MB/s;
- SHA PASS.

EXP-39 retained two predictive candidates inside the fused traversal.

EXP-39A:

- 65,321,697 bytes;
- 30.82105%;
- compression approximately 22.33 MB/s;
- decompression approximately 124.17 MB/s;
- SHA PASS.

Decision:

- EXP-37A = Max direct backend;
- EXP-39A = balanced fused research checkpoint;
- AURORA Media remains on direct EXP-37A because its specialized frontend already removes much of the structure the general router would search for.

## 63. EXP-40 through EXP-43 — structural diagnostics

### EXP-40 Residual Difficulty Map

Chunks were measured using:

- byte entropy;
- geometry-aware residual entropy;
- equality rates at lags 1, 16 and 256;
- printable-text fraction;
- excess size relative to a 26% target.

This changed the research method from blind transform testing to targeted diagnosis.

### EXP-41 Dual Residual Surface Oracle

Per-chunk reversible delta-lag transforms at 16 and 256 were compared against BASE.

Observed oracle gain:

- approximately 342,358 bytes on the chunked test;
- almost all of the gain came from x-ray;
- D256 did not become broadly useful.

### EXP-42 Multi-Lag Residual Surface Oracle

Tested lags:

```text
1, 4, 16, 64, 256, 1024
```

Major findings:

- x-ray strongly favored lag 4;
- mr strongly favored lag 1024;
- total oracle gain on the selected difficult subset exceeded 1.14 MB.

### EXP-43 Structural Reordering Oracle

Delta and transposition were combined.

Important results:

- x-ray: D4 + T4 saved approximately 1,209,262 bytes;
- mr: D1024 + T1024 saved approximately 539,714 bytes;
- total gain on the tested subset: approximately 1,784,150 bytes.

This established that some datasets contain strong field/record geometry that a flat byte stream hides.

## 64. EXP-44 through EXP-48 — structural routing

EXP-44 turned structural oracle experiments into an end-to-end decodable router.

For every 512 KiB chunk, candidate reversible representations were compressed and the smallest final payload selected.

EXP-44 full Silesia:

- 63,581,600 bytes;
- 30.0000123%;
- SHA PASS.

Later routing experiments added numeric/field transforms and adaptive period surfaces.

Important checkpoints:

- EXP-46: 63,439,947 bytes, 29.9331755%;
- EXP-47 oracle: 63,227,225 bytes, 29.8328058%;
- EXP-48 end-to-end router: 63,201,140 bytes, 29.8204980%;
- SHA PASS.

EXP-48 was the best validated general-purpose ratio checkpoint at this stage.

Its low measured encoding throughput is not representative of the KHEPRI core: it repeatedly encodes candidate representations in order to discover the smallest one.

This router is a research/oracle mechanism, not the intended final fast selector.

## 65. EXP-49 and EXP-50R — rejected structural branches

Bit-plane, nibble separation and XOR+bit-plane transforms were tested on the remaining difficult data.

The gain was concentrated in data already handled better by EXP-48 structural modes.

Therefore the extra syntax/complexity was not promoted.

A 28-byte-record experiment for the SAO dataset also failed to beat BASE.

Decision:

```text
REJECTED
```

These results are retained to prevent repeated experimentation.

---

# PART XX — HIGH-SPEED KHEPRI LINE

## 66. Change of optimization objective

After achieving a sub-30% structural-router checkpoint, the project temporarily changed its main optimization objective from compression ratio to throughput.

Target:

```text
compression   >= 100 MB/s
decompression ~= 180-200 MB/s or higher
```

The target refers to the core/profile implementation, not to an oracle router that evaluates multiple complete encodings.

## 67. Historical evidence that the target is feasible

Earlier KHEPRI checkpoints had already demonstrated high throughput on the reconstructed development corpus.

Examples:

- EXP-20 compression approximately 95.6 MB/s, decompression approximately 163.2 MB/s;
- EXP-21 compression approximately 110.3 MB/s, decompression approximately 174.2 MB/s;
- EXP-22 synthetic/mixed tests showed substantially higher decompression on some data.

Therefore 100/200-class throughput is not treated as an arbitrary target. The research challenge is recovering that speed while retaining as much of the later compression work as possible.

## 68. FAST-A

FAST-A removed expensive ratio-oriented features:

- no structural multi-probe router;
- no predictive dual-match second scan;
- reduced search depth;
- reduced lazy behavior;
- sparse predictor activity.

Silesia result:

- raw: 211,938,580 bytes;
- compressed: 66,547,621 bytes;
- ratio: 31.3994842%;
- compression: 42.23 MB/s;
- decompression: 116.43 MB/s;
- SHA PASS.

This result demonstrated that match-search reduction alone was not sufficient.

## 69. Per-file throughput diagnosis

FAST-A throughput varied strongly by data type.

Examples:

- nci: approximately 106 MB/s encode and 299 MB/s decode;
- xml: approximately 70 MB/s encode and 195 MB/s decode;
- x-ray: approximately 18.7 MB/s encode and 59 MB/s decode;
- sao: approximately 24.3 MB/s encode and 55 MB/s decode;
- ooffice: approximately 26.7 MB/s encode and 78 MB/s decode.

Important conclusion:

The KHEPRI core can already exceed the throughput target on favorable data. The bottleneck is data-dependent hot-path work, especially literal/residual processing on difficult chunks.

## 70. FAST-D — literal-path bypass

FAST-D was a diagnostic and optimization checkpoint.

The expensive predictor/residual literal path was bypassed symmetrically and literals were handled through a simpler raw-model path while match coding remained active.

Result:

- compressed: 65,571,285 bytes;
- ratio: 30.9388149%;
- compression: 64.63 MB/s;
- decompression: 181.67 MB/s;
- SHA PASS.

This was a major throughput improvement over FAST-A.

The decompression target was effectively reached.

Compared with EXP-37A direct:

- EXP-37A ratio: approximately 30.8148%;
- FAST-D ratio: approximately 30.9388%;
- ratio cost: approximately +0.124 percentage points;
- compressed-size difference: roughly +263 KiB on Silesia.

Compared with the structural-router EXP-48:

- ratio cost: approximately +1.118 percentage points;
- size cost: approximately +2.37 MB.

This is an important distinction: most of the apparent loss relative to EXP-48 comes from removing the expensive structural multi-probe router, not from the literal fast-path alone.

## 71. FAST-E — reduced match search

FAST-E kept the FAST-D literal bypass but further reduced match-search depth.

Result:

- ratio: 31.5408761%;
- compression: 63.62 MB/s;
- decompression: 143.95 MB/s;
- SHA PASS.

It did not improve compression throughput and materially degraded both ratio and decode speed.

Decision:

```text
REJECTED
```

Conclusion:

The remaining compression bottleneck cannot be solved by simply shortening the hash-chain search further.

## 72. Current speed checkpoint and next optimization target

Current promoted speed research checkpoint:

```text
FAST-D
64.63 MB/s encode
181.67 MB/s decode
30.9388% Silesia ratio
SHA PASS
```

The next performance work should profile and optimize:

- arithmetic/range coder hot loops;
- probability-model update frequency;
- model memory layout and cache locality;
- branch behavior in token/literal encoding;
- context lookup cost;
- per-symbol renormalization overhead;
- possible batching of independent coding operations;
- thread scheduling and chunk parallelism.

The project must not blindly disable features without profiling because FAST-E demonstrated that reducing algorithmic work can still worsen effective throughput through changed token/literal distribution and decoder behavior.

---

# PART XXI — FORMAL RESEARCH RULES GOING FORWARD

## 73. Separate ratio, balanced and speed profiles

The project now maintains three conceptually distinct goals.

### Ratio / Max research

Purpose:

- maximize compression;
- structural routing/oracle work allowed;
- speed may be temporarily sacrificed during research.

Reference general checkpoint:

```text
EXP-48 structural router
29.8205% Silesia
```

### Direct media backend

Purpose:

- stable backend for already-conditioned audio/video residual streams;
- avoid redundant general-purpose transforms.

Reference:

```text
EXP-37A Predictive Dual Match
```

### Fast profile

Purpose:

- real-time/high-throughput applications;
- current target >=100 MB/s encode and ~200 MB/s decode;
- compression ratio is secondary but still measured.

Reference:

```text
FAST-D
```

No profile automatically replaces another.

## 74. Checkpoint discipline

Every promoted checkpoint must record:

1. exact source revision;
2. compiler and build flags;
3. corpus identification;
4. raw byte count;
5. compressed byte count;
6. ratio;
7. encode throughput;
8. decode throughput;
9. SHA/roundtrip status;
10. configuration macros/parameters;
11. comparison against the previous checkpoint;
12. promotion or rejection decision;
13. reason for the decision.

## 75. Scientific interpretation discipline

A smaller compressed file does not by itself prove a general algorithmic improvement.

The project distinguishes:

- corpus-specific gain;
- backend-specific coupling;
- generalizable mechanism;
- oracle-only potential;
- production-feasible implementation.

Likewise, a fast synthetic test does not prove production throughput.

Claims must identify:

- test corpus;
- hardware/runner context;
- thread count;
- whether the result is a median or single run;
- whether candidate-search overhead is included.

## 76. Intellectual-property discipline

The repository intentionally separates:

- standard/background techniques;
- independently implemented code;
- project-specific combinations/architectures;
- research hypotheses;
- candidate inventions.

No document should claim patentability merely because a technique was independently developed.

Potentially distinctive areas worth prior-art review include the interaction among:

- prediction-aware LZ match selection;
- multidimensional residual cost fields;
- topology-aware encoder-only parser decisions;
- KHEPRI-specific media residual serialization;
- adaptive state/reset horizons driven by backend behavior;
- future low-cost structural-mode prediction replacing brute-force oracle routing.

---

# PART XXII — REPOSITORY GOVERNANCE

## 77. Canonical branch roles

```text
main
    general KHEPRI/Silesia research lineage

research/khepri-stream-codec
    AURORA Media audio/video backend, container, stream and media research
```

Do not merge experimental media code into `main` merely for convenience.

Do not copy general-purpose experimental files into the media production source tree.

## 78. Canonical source locations

Production-candidate C++20 code:

```text
src/cpp/aurora_media/
```

Executable Python reference:

```text
src/python/reference/
```

Research:

```text
research/audio/
research/video/
research/backend/
```

Measured results:

```text
results/audio/
results/video/
results/benchmarks/
```

Long-lived engineering documentation:

```text
docs/
```

The former `streaming/` implementation tree has been fully migrated and removed from the tracked repository. Historical versions remain available through Git history.

## 79. Naming rule

Canonical files use descriptive names that state role, not transient implementation detail.

Good examples:

```text
AuroraMediaContainer.cpp
aurora_media_container.py
AURORA_MEDIA_TECHNICAL_MASTER.md
KSV05_ADAPTIVE_ROUTING_RESULTS.md
```

Experiment IDs remain only where chronology itself is useful:

```text
ks06_plane_sparsity.py
ksv05_adaptive_gop_router.py
```

Avoid ambiguous names such as:

```text
test2.py
new_codec.py
final_final.py
results.json
exp_latest.py
```

## 80. Final current project state

At this checkpoint the project has:

- a validated lossless audio research pipeline;
- a validated lossless video research pipeline;
- a project-owned AUM container;
- project-owned AUS1 stream framing;
- a Python executable binary/reference implementation;
- a C++20 native container/session/stream backend;
- Python/C++ binary interoperability;
- reproducible benchmark infrastructure;
- preserved positive and negative research history;
- a direct KHEPRI media backend based on EXP-37A;
- a general-purpose structural-router research line reaching 29.8205% on Silesia;
- a high-speed research line currently at FAST-D, approximately 64.63 MB/s encode and 181.67 MB/s decode on Silesia;
- an explicit repository structure separating product code, research, results and documentation.

The next engineering work should continue from these checkpoints rather than recreating older experiments.
