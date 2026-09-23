# KHEPRI Stream — IP / Prior-Art Register

> Research engineering record. This is not a legal opinion and does not establish patentability.

## Rule

Every promoted KHEPRI Stream mechanism must be classified as one of:

- **BACKGROUND** — established technique used only as infrastructure or a control.
- **CANDIDATE-IP** — a KHEPRI-specific mechanism whose novelty must be searched and documented.
- **REJECTED-IP** — useful technically, but too close to known techniques to be treated as an invention.

A performance win alone is not enough for CANDIDATE-IP status.

## Background techniques — not claimed as KHEPRI inventions

The following are explicitly treated as known/background:

- block-wise linear prediction / LPC;
- adaptive selection of predictor order or coefficients;
- prediction residual coding;
- entropy coding of audio residuals;
- first-order and higher-order finite differences;
- reversible stereo decorrelation / mid-side style transforms;
- Golomb/Rice-style residual coding;
- generic bit-plane coding;
- generic spatial and temporal prediction in video;
- generic motion-compensated prediction;
- generic transform + quantization coding.

Prior-art anchors already identified include:
- US8050915B2 / US8032368B2: block switching and adaptive linear prediction for lossless audio;
- EP1859531A4: predictor + residual + entropy coding and inter-channel correlation for lossless audio;
- US6356213B1: cascaded/adaptive prediction for lossless encoding;
- RFC 9639 (FLAC): fixed/linear predictors and residual coding.

These references are not exhaustive.

## Candidate IP family KS-RG — KHEPRI Residual Geometry

### Technical problem

A generic byte-oriented backend does not automatically see media residual structure in a byte layout that matches its own match-distance and probability topology. KHEPRI EXP-33H has a measured, deliberately modeled distance topology around 16-wide lines and 256-wide planes.

### Candidate mechanism

**KHEPRI Media Residual Lattice (KMRL)**

Instead of merely serializing prediction residuals, KMRL maps a reversible residual field into tiles whose serialization is intentionally coupled to KHEPRI's native distance topology.

Initial research form:

1. split a media block into 256-position residual tiles;
2. arrange each tile conceptually as 16 x 16 positions;
3. classify mapped residual magnitudes into bounded payload classes;
4. serialize the class field before class-specific magnitude planes;
5. serialize multi-byte magnitudes plane-wise rather than sample-wise;
6. keep 16- and 256-position recurrence visible in the byte stream;
7. choose the predictor for each component/tile using the cost of the resulting residual-field representation, not LPC variance alone;
8. reset tile prediction state so recovery boundaries are deterministic.

The candidate inventive concept is **not** any individual predictor, class code, bit plane, or tile size in isolation. The research hypothesis is the coupling between:
- reversible media prediction,
- residual-field geometry,
- topology-shaped serialization,
- and a backend whose distance model is designed around the same lattice.

### Why this is being investigated

EXP-33H already uses a native KHEPRI distance topology with 16-wide line and 256-wide plane relationships. KMRL attempts to make audio/video residual structure inhabit that topology deliberately rather than accidentally.

### Patentability status

**UNDETERMINED.**

A novelty/inventive-step search must specifically investigate:
- entropy coders that reorder residual bytes based on an LZ match-distance lattice;
- tiled residual class fields aligned to compressor dictionary distances;
- joint optimization of media predictor choice and downstream LZ/topological match cost;
- plane-wise residual serialization designed for a specific dictionary-distance model.

Until that search is complete, documentation must say “candidate IP” or “proprietary research mechanism”, never “patented” or “patentable”.

## Disclosure discipline

Before public release of detailed candidate-IP algorithms:
1. preserve dated source history and benchmark evidence;
2. record inventors/contributors;
3. record the first working commit and test run;
4. perform a focused patent/literature search;
5. obtain professional patent advice for jurisdictions of interest before relying on public-disclosure grace periods.
