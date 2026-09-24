# Workflow Policy — AURORA Compressor / KHEPRI

**Branch:** `project/aurora-compressor`

## Purpose

GitHub Actions is part of the reproducibility system. Workflows should reproduce a named experiment, validation or benchmark; they are not a storage mechanism.

## Path policy

Workflow scripts must use the canonical locations:

- EXP generators → `research/generators/general/`
- FAST/SPEED generators → `research/generators/speed/`
- EXP research → `research/experiments/`
- validation → `research/validation/`
- oracles → `research/oracles/`
- routers → `research/routers/`
- diagnostics → `research/diagnostics/`
- speed harnesses → `research/speed/`
- Silesia harness → `benchmarks/silesia/`
- competitor benchmarks → `benchmarks/competitors/`
- source fragments → `engine/source_parts/`

No workflow should reintroduce root-level research scripts.

## Trigger policy

Historical experiments should prefer `workflow_dispatch` when they no longer require automatic validation.

Active research may use narrow path-filtered push triggers.

Avoid broad push triggers on historical workflows.

## Result discipline

Every active benchmark workflow must:
- fail on roundtrip/SHA mismatch;
- identify the checkpoint under test;
- preserve measured output as an artifact when useful;
- compare against the current reference when the experiment is intended as a replacement.

## Experiment discipline

One optimization hypothesis should correspond to one focused validation cycle. Failed experiments are documented and then stopped before a new hypothesis begins.
