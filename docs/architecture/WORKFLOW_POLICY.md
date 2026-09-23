# Workflow Policy — AURORA Media / KHEPRI

## Purpose

GitHub Actions is part of the reproducibility system, not an archive browser. New workflows must have a clear role and stable name.

## Workflow classes

### Active backend validation

Names should begin with `aurora_` and describe the subsystem, for example:

- `aurora_media_v01.yml`
- `aurora_media_cpp_interop.yml`
- `aurora_full_stack_benchmark.yml`
- `aurora_audio_packet_horizon_v03.yml`

These workflows validate canonical code under `src/` and `tests/`.

### Active benchmark workflows

Names must describe the benchmark rather than the date or temporary hypothesis.

Example:

- `khepri_major_codec_benchmark.yml`

### Historical research workflows

KS/KSV workflow names retain their experiment IDs because they reproduce published internal checkpoints.

They are historical/research assets, not production CI.

### General KHEPRI inherited workflows

EXP-numbered workflows belong to the wider compressor research lineage.

They may remain while reproducibility depends on the root experiment scripts, but new AURORA Media production work must not be added to them.

## Trigger policy

Historical experiments should prefer `workflow_dispatch` once their checkpoint is complete.

Active backend validation may run on path-filtered push events.

Avoid broad push triggers for old experiments because they create unrelated runs and obscure current CI state.

## Naming policy

Use:

```text
product_or_engine + subsystem + purpose
```

Examples:

```text
aurora_media_cpp_interop.yml
khepri_stream_ksv05.yml
khepri_major_codec_benchmark.yml
```

Do not create ambiguous workflow names such as:

```text
test.yml
new.yml
benchmark2.yml
final.yml
```

## Promotion policy

When an experiment is promoted into canonical backend code:

1. add/extend a canonical test under `tests/`;
2. add or update an active backend workflow;
3. keep the old experiment workflow only if it is still needed for reproducibility;
4. otherwise archive its method/result in documentation and stop triggering it automatically.

## Current workflow state

The AURORA Media source migration is complete.

Historical KS/KSV workflows:
- use canonical research paths;
- are manual reproducibility jobs unless still serving active validation;
- may create temporary runtime output directories, but do not depend on tracked legacy source.

Active AURORA backend workflows continue to target `src/`, `tests/`, `research/`, `benchmarks/` and `results/`.

General EXP-numbered workflows remain part of the wider KHEPRI research lineage and are managed separately.
