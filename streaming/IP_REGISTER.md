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
- generic residual sign/magnitude separation;
- fixed byte-plane transposition of sample/residual words;
- generic raster/sample reordering before dictionary compression;
- generic spatial and temporal prediction in video;
- generic motion-compensated prediction;
- generic transform + quantization coding.

Prior-art anchors already identified include:
- US8050915B2 / US8032368B2: block switching and adaptive linear prediction for lossless audio;
- EP1859531A4: predictor + residual + entropy coding and inter-channel correlation for lossless audio;
- US6356213B1: cascaded/adaptive prediction for lossless encoding;
- RFC 9639 (FLAC): fixed/linear predictors, folded residuals and Rice residual coding;
- US8386271B2: residual decomposition including bit-plane coding;
- EP2487798A1: sample-bit alignment/reformatting to improve dictionary compression of audio/image data;
- US6668093B2: reordering raster data to improve dictionary-based compression.

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

### Prior-art narrowing after KS-04

KS-04 showed that 256-position magnitude planes materially improve EXP-33H. However, the prior-art search also found earlier disclosures of bit-plane residual decomposition, sample-bit alignment for dictionary coding, and raster reordering for dictionary coding. Therefore **fixed KMRL plane serialization by itself is not treated as the core invention**.

The candidate IP is narrowed to a more KHEPRI-specific mechanism:

## Candidate IP family KS-TA — Topology-Adaptive Residual Arrangement

Working name: **KHEPRI Topology-Adaptive Residual Permutation (KTARP)**.

For each reversible residual tile/plane, the encoder evaluates a bounded family of reversible arrangements and selects an arrangement using a cost function derived from the *actual favored distance topology of the downstream KHEPRI backend*, including neighborhoods around 16 and 256. The arrangement identifier is transmitted so decoding remains deterministic.

The research distinction to test is not generic reordering. It is the closed-loop coupling of:

1. a media residual field;
2. a finite reversible permutation family;
3. a compressor-specific distance-affinity objective;
4. the exact distance neighborhoods modeled by the downstream KHEPRI parser/coder;
5. chunk-local deterministic selection compatible with streaming recovery.

KS-05 must compare fixed FULL256 against topology-adaptive arrangements. If no measurable improvement occurs, KS-TA is not promoted.

## Disclosure discipline

Before public release of detailed candidate-IP algorithms:
1. preserve dated source history and benchmark evidence;
2. record inventors/contributors;
3. record the first working commit and test run;
4. perform a focused patent/literature search;
5. obtain professional patent advice for jurisdictions of interest before relying on public-disclosure grace periods.


## KS-05 disposition — KTARP

Status: **REJECTED-IP / NOT PROMOTED IN CURRENT FORM**

Measured on the KS-03/04 real-audio checkpoint:
- fixed FULL256 baseline: 5,552,105 bytes;
- best KTARP adaptive variant: 5,596,006 bytes;
- delta: +0.791% (worse).

The tested topology-affinity objectives do not provide enough predictive value for final EXP-33H archive size. The source and results remain preserved as negative research evidence, but KTARP is not part of the promoted KHEPRI Stream technical core.

A future topology-adaptive family would require a materially different cost model and fresh prior-art review before returning to CANDIDATE-IP status.
