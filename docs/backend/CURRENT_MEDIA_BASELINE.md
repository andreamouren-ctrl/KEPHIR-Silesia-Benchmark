# Current AURORA Media Baseline

Date: 2026-09-23

## Audio production/research baseline

Active codec path:
- PCM s16le stereo 48 kHz
- reversible stereo decorrelation
- KMRL
- FULL256
- TAIL16
- KHEPRI EXP-37A
- fixed 2-second recovery packets
- AUM v0.1

Current full-AUM Sintel result:
- 5,546,982 bytes
- bit-exact
- canonical FULL256 + TAIL16 bridge revalidated on 2026-09-26

KASH-01 research result:
- 5,541,589 bytes
- -0.0968% vs fixed 2 s
- not yet promoted because decision search requires duplicate candidate encodes

## Video baseline

Active operational codec path:
- YUV420p8
- 20-frame routing horizon
- TEMP candidate
- cached MC8R4 motion/residual field
- cheap MC symbol predictor:
  - mean signed residual magnitude < 2.60 -> ZZ_INTER
  - otherwise -> MOD8
- KHEPRI EXP-37A
- AUM v0.1

Operational router: **KSV-09C**

KSV-09C pre-AUM aggregate:
- 9,727,633 bytes

Full AUM aggregate:
- **9,730,778 bytes**

KSV-08 oracle full-AUM aggregate:
- 9,729,032 bytes

Operational penalty versus oracle:
- 1,746 bytes
- +0.01795%

True wall-clock comparison:
- KSV-08: 62.7543 s
- KSV-09C: 34.8628 s
- speedup: 1.80x
- wall-clock reduction: 44.45%

FFV1 aggregate on the same diagnostic corpus:
- 10,357,351 bytes

KSV-09C full AUM remains approximately **6.05% smaller than FFV1** on this limited three-clip diagnostic corpus.

KSV-08 remains the research oracle for validating future cheap predictors.

This is not a general codec superiority claim.

## Backend

- KHEPRI EXP-37A
- AUM v0.1
- AUS1 stream framing
- C++20 container/session/stream backend
- Python executable reference
- Python <-> C++ binary interoperability
- typed codec interfaces
- resource limits
- corruption matrix
- in-process KHEPRI buffer contract

## Immediate priorities

1. replace brute-force KSV-08 three-way trial with a cheaper mode predictor;
2. derive a cheap KASH reset-benefit estimator;
3. extract real EXP-37A encode/decode into the in-process IKhepriBackend contract;
4. continue motion/residual research for medium/high-motion video.


## 4K streaming readiness

Architecture now includes:
- 3840x2160 tile planning;
- 256x240 default tiles;
- 135 tiles/frame at 4K;
- bounded concurrent tile workers;
- bounded in-flight scheduler/backpressure;
- Streaming4K / Balanced / MaxCompression profiles.

Current status:
- architecture/memory scheduling: validated;
- realtime 4K throughput: not yet validated;
- native hot-path port remains required.

See:
`docs/backend/AURORA_4K_STREAMING_READINESS.md`


## Native 4K hot-path progress

Validated C++20 components:
- 4K tile planner
- bounded tile scheduler/backpressure
- Streaming4K / Balanced / MaxCompression profiles
- MOD8 residual mapping
- ZZ_INTER reversible residual mapping
- KSV-09C mean signed residual predictor
- MC8R4 motion search
- motion map generation
- Y/U/V residual generation
- lossless MC8R4 reconstruction
- synthetic 4K tile residual roundtrip

Latest C++20 backend validation:
- GitHub Actions run 35856003939
- result: PASS
- build quality gate: -Wall -Wextra -Werror

The dominant remaining non-native dependency in the active research path is KHEPRI EXP-37A execution through the CLI/file staging path.

Next backend gate:
- expose actual EXP-37A encode/decode through IKhepriBackend using memory buffers;
- connect native video tile motion/residual output directly to that in-process backend;
- run first native 4K raw YUV420p smoke benchmark.


## 2026-09-26 exact motion fast-path checkpoint

Validation:
- GitHub Actions run 36215128505
- result: PASS
- exhaustive-equivalence regression: PASS
- benchmark fingerprints: identical

MC8R4 optimization:
- terminate ordered candidate search when SAD reaches 0;
- preserves the exhaustive winner because SAD cannot be negative;
- preserves the historical first-minimum tie rule;
- A/B reference path remains available through `AURORA_DISABLE_EXACT_MOTION_FASTPATH`.

Measured native tile-motion speed:
- static: 2.775x, 63.97% time reduction;
- low motion: 1.613x, 37.99% time reduction;
- noise: 0.989x, approximately neutral.

Decision:
- promote Exact Motion Fast Path to the AURORA Media research baseline;
- next exact-speed target: remove tile extraction/copy overhead through reference-view/zero-copy motion input.


## 2026-09-26 interior motion fast-path checkpoint

Validation:
- GitHub Actions run 36219179822
- result: PASS
- regression test: PASS
- A/B output fingerprints: identical
- bitstream input equivalence: PASS

Optimization:
- interior MC8R4 blocks skip redundant per-candidate boundary checks;
- edge blocks retain the historical validation path;
- candidate set/order, SAD score and first-minimum tie rule are unchanged.

Native tile-motion timing:
- static: 1.003x, 0.34% time reduction;
- low motion: 1.073x, 6.80% time reduction;
- noise/high activity: 1.177x, 15.02% time reduction.

Decision:
- promote Interior Motion Fast Path.

Rejected CPU experiment:
- zero-copy full-frame region MC8R4, run 36219053497;
- correctness PASS;
- removed 37,324,800 copied bytes/inter-frame at 4K;
- total motion encode+decode became ~2.3% slower because compact tile buffers improve CPU cache locality;
- do not promote zero-copy on CPU; retain for future GPU/direct-frame research.

Next exact-speed targets:
- lower-instruction SSE2 SAD evaluation;
- SIMD residual generation/reconstruction;
- re-run native 4K full-pipeline throughput after each isolated promotion.


## 2026-09-26 residual SIMD checkpoint

Validation:
- isolated benchmark run 36219419153
- full native pipeline run 36219468195
- bitstream/output fingerprint equivalence: PASS
- full-pipeline payload equivalence: PASS

Optimization:
- SSE2 byte-wise luma residual subtraction in the encoder;
- SSE2 byte-wise luma reconstruction addition in the decoder;
- modulo-256 behavior is exactly preserved;
- chroma remains scalar.

Isolated 256x240 tile speedup:
- static: 1.741x encode / 2.111x decode / 1.899x combined;
- low motion: 1.331x / 2.080x / 1.533x;
- noise/high activity: 1.276x / 2.114x / 1.447x.

Full native 4K / 4-worker pipeline:
- scalar residual: 5.9476 fps encode, 51.1203 fps decode, 5.32774 fps total;
- SSE2 residual: 6.04301 fps encode, 59.2361 fps decode, 5.48360 fps total;
- speedup: 1.016x encode, 1.159x decode, 1.029x total;
- payload unchanged: 256,727 bytes.

Decision:
- promote residual SIMD.

Rejected during the same cycle:
- paired-row SSE2 SAD (run 36219312895);
- bitstream correct but -11.28% low-motion and -16.59% noise performance;
- retain one-row SSE2 SAD.

Current primary performance bottleneck:
- encode-side MC8R4 motion search.


## 2026-09-26 canonical audio bridge restoration

Validation:
- GitHub Actions run 36220062460
- explicit FULL256 + TAIL16 frontend roundtrip: PASS
- complete AUM horizon roundtrip: PASS

Root cause fixed:
- the bridge had drifted to generalized KMRL v2 for s16 PCM;
- the promoted FULL256 + TAIL16 geometry was documented but not wired into the packet bridge.

Canonical s16 path is now explicit KRL2 layout 4:
- KMRL carry prediction;
- FULL256;
- TAIL16;
- KHEPRI EXP-37A;
- AUM v0.1.

Recovery-horizon results:
- 200 ms: 5,825,154 bytes;
- 500 ms: 5,715,715 bytes;
- 1000 ms: 5,599,488 bytes;
- 2000 ms: 5,546,982 bytes.

The 2000 ms result is only 24 bytes above the historical 5,546,958-byte checkpoint
(~0.00043%) while removing the research-time monkey-patched layout ambiguity.

Decision:
- promote the wiring fix;
- invalidate KASH-02 predictor conclusions collected on the generalized frontend;
- rerun adaptive recovery prediction only on this restored canonical path.


## 2026-09-26 KASH-02 canonical adaptive recovery checkpoint

Validation:
- GitHub Actions run 36224542571
- all AUM outputs bit-exact
- production duplicate candidate encodes: 0

Canonical fixed 2-second baseline:
- 5,546,982 bytes

Research oracle:
- 5,541,642 bytes
- 5,340 bytes smaller than fixed 2 s
- approximately 0.0963% gain
- oracle search cost: 27.475330 s

Cheap PCM predictor:
- rule: diff_change >= 2.0409084219
- 5,543,634 bytes
- 3,348 bytes smaller than fixed 2 s
- approximately 0.0604% gain
- recovers 62.697% of oracle gain
- PCM decision cost: 0.039369 s
- approximately 698x cheaper than oracle search

Decision:
- research result accepted;
- rule is not yet a production baseline because it was learned/evaluated on one source family;
- next gate: KASH-03 multi-corpus unseen validation.


## 2026-09-26 KASH-03 unseen multi-corpus checkpoint

Validation:
- GitHub Actions run 36224815221
- Elephants Dream / Big Buck Bunny / Tears of Steel
- frozen KASH-02 rule; no retraining
- all outputs bit-exact
- production duplicate candidate encodes: 0

Aggregate:
- fixed 2 s: 8,966,978 bytes
- oracle: 8,882,472 bytes
- predictor: 8,959,223 bytes
- available oracle gain: 84,506 bytes
- predictor gain: 7,755 bytes
- oracle gain recovered: 9.177%

Per-source:
- Elephants Dream: +863-byte predictor regression (+0.035897%)
- Big Buck Bunny: 0-byte predictor gain while oracle exposes 63,885 bytes
- Tears of Steel: -8,618 bytes (-0.251679%), 42.119% oracle recovery

Decision:
- do not promote the frozen KASH-02 rule;
- adaptive horizon remains valuable, but the single-feature threshold does not generalize;
- next gate: KASH-04 multi-feature, leave-one-source-out predictor with conservative false-split cost.


## 2026-09-26 KASH-04 conservative recovery checkpoint

Validation:
- GitHub Actions run 36225130012
- four 30-second lossless source families
- fixed 2-second macro-windows, optionally split into 1 s + 1 s
- all outputs bit-exact
- production duplicate candidate encodes: 0

Fit-all diagnostic:
- fixed aggregate: 12,133,166 bytes
- macro oracle: 12,106,992 bytes
- predictor: 12,108,096 bytes
- predictor gain: 25,070 bytes
- oracle gain recovered: 95.782%

Leave-one-source-out procedure:
- Sintel: 0-byte gain
- Elephants Dream: -262 bytes
- Big Buck Bunny: -232 bytes
- Tears of Steel: -18,892 bytes

Decision:
- no production promotion;
- fixed 2-second recovery remains the canonical production baseline;
- KASH stays research-only until a substantially broader corpus exists;
- do not increase classifier complexity on the current small corpus.


## 2026-09-26 hardware-adaptive worker autotune checkpoint

Validation:
- GitHub Actions run 36224964385
- unit policy test: PASS
- full native 4K pipeline: PASS
- payload unchanged: 256,727 bytes

Runner:
- hardware_concurrency: 4
- Balanced profile cap: 6
- valid probe candidates: 1, 2, 4

Measured 4K autotune probes:
- 1 worker: 1.96857 total fps
- 2 workers: 3.89652 total fps
- 4 workers: 5.58908 total fps

Selection:
- selected: 4 workers
- fastest valid candidate: 4 workers
- selection overhead versus fastest: 0.000%

A separate manual 8-worker run reached 5.63084 total fps, only ~0.75% above four workers while
oversubscribing the runner's reported four hardware threads.

Decision:
- promote Worker Autotune infrastructure;
- do not hard-code a universal worker count;
- production policy is to probe a small bounded candidate set per machine/profile and select the
  fastest non-oversubscribed configuration, preferring fewer workers when timings are effectively tied.
