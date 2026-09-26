# KEPHIR 2 Core — Product Engineering Plan

**Branch:** `development/kephir-2-core`  
**Base:** `research/exp77-adaptive-layout`  
**Role:** production-oriented development line for the general-purpose lossless compressor.

## Product objective

KEPHIR 2 must earn adoption through measurable behavior on real heterogeneous archives, not through a single-corpus ratio claim.

The product thesis is:

> Analyze the archive, learn which decisions work for the workload, and automatically choose the compression strategy while keeping archives self-contained and fully portable.

## Non-negotiable properties

1. Exact lossless roundtrip with SHA-256 verification.
2. Decoder never depends on Factory or Local Experience.
3. Automatic mode is the primary user experience.
4. Research checkpoints remain reproducible but are not runtime dependencies.
5. Production code moves toward one native C++ core with no mandatory subprocess or temporary-file orchestration.
6. Every promoted change must report size, ratio, compression speed, decompression speed, memory where available, and selection regret where routing is involved.
7. Existing KEPHIR 1.0 release branches remain untouched.

## Product differentiation

KEPHIR 2 is an adaptive archive engine rather than a single fixed stream codec.

The product stack is:

```text
Archive Analyzer
  -> Global Strategy Router
  -> Content Classification
  -> Directory Layout
  -> Grain Selection
  -> Reversible Structural Transform
  -> Cost-aware Parallel Scheduler
  -> Predictive LZ Parser
  -> Adaptive Entropy Coding
  -> Indexed Self-contained Archive
```

Factory, Local and Session Experience are encoder-side optimization knowledge. They may reduce exploration and improve decisions, but the archive must contain everything required for decoding.

## Development phases

### Phase A — Global Router

Replace EXP-77's static metadata rule with bounded representative probing.

Required metrics:
- selected layout;
- oracle layout;
- selection regret bytes;
- probe bytes;
- probe time;
- total routing overhead;
- final archive bytes.

Promotion target: zero or near-zero aggregate regret across repository, Silesia and later mixed/incompressible workloads without probe cost scaling linearly with archive size.

### Phase B — Native production core

Create a stable native source tree:

```text
src/
  core/
  transforms/
  routing/
  learning/
  archive/
  parallel/
```

The current EXP generator chain remains available only for reproducibility.

### Phase C — KPF2

Add indexed block/group metadata, per-block integrity and random-access extraction foundations.

### Phase D — Product profiles

Expose:
- AUTO
- FAST
- BALANCED
- MAX

AUTO chooses the strategy. Profiles specify an optimization objective, not a hand-tuned list of internal switches.

### Phase E — Commercial benchmark matrix

Evaluate real workloads:
- source repositories;
- many-small-file trees;
- mixed office/project directories;
- logs and text datasets;
- structured binaries;
- already-compressed/incompressible data;
- canonical Silesia.

Compare against current mainstream general-purpose compressors using same-machine A/B runs.

## Immediate milestone

**EXP-78 — Bounded Representative Layout Probe**

Goal: replace the static EXP-77 layout selector with a bounded two-stage sample probe and measure regret against the full-layout oracle.
