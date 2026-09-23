# Canonical Path Migration Status

## Status

**COMPLETE for AURORA Media tracked source.**

The former `streaming/` source tree has been removed from the branch after migration to canonical locations.

Git history remains the archive for pre-migration implementations.

## Canonical locations

- C++20 backend → `src/cpp/aurora_media/`
- Python executable/reference implementation → `src/python/reference/`
- C++/Python tests → `tests/`
- audio experiments/lab → `research/audio/`
- video experiments/diagnostics/lab → `research/video/`
- KHEPRI/media integration research → `research/backend/`
- reusable benchmarks → `benchmarks/`
- measured results → `results/`
- canonical engineering documentation → `docs/`

## What was migrated

- native AUM container backend;
- AUS1 stream backend;
- media session backend;
- Python container/reference pipeline;
- converter/reference orchestration;
- codec bridge;
- audio KS experiments;
- video KSV experiments;
- major codec benchmark;
- KS/KSV measured result documents;
- C++ tests;
- Python interoperability/end-to-end tests;
- IP register;
- backend baseline documents.

## Duplicate cleanup

Byte-identical files that existed both in `streaming/` and canonical directories were deleted after SHA comparison.

Historical files that differed from their canonical descendants were also removed from the working tree only after confirming an evolved canonical replacement. Their exact historical versions remain available in Git history.

## Workflow migration

Historical KS/KSV workflows now execute canonical scripts.

Completed historical workflows are manual (`workflow_dispatch`) rather than broad automatic push jobs.

They use `PYTHONPATH` to expose canonical research modules without reintroducing duplicate source files.

Some historical scripts still use runtime output names such as `streaming/ks06_out`. Those paths exist only inside ephemeral CI workspaces and do not represent tracked legacy source.

## General-purpose KHEPRI root research

Root `exp*.py`, `make_exp*_source.py`, Silesia benchmark scripts and their workflows are intentionally retained.

They belong to the wider general-purpose KHEPRI research lineage and are required for checkpoint reproducibility. They are not AURORA Media production modules.

A future general-KHEPRI repository migration should be coordinated separately from the completed media migration.

## Rule for all new work

- production/backend C++ → `src/cpp/aurora_media/`
- Python reference → `src/python/reference/`
- experiments → `research/`
- benchmark harnesses → `benchmarks/`
- measured results → `results/`
- long-lived documentation → `docs/`

No second implementation tree may be introduced.
