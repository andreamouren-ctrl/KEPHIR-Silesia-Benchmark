# Repository Audit — 2026-09-23

## Objective

Turn the historical research tree into a repository where a developer can answer immediately:
- what code is active;
- what code is a reference model;
- what is experimental;
- what result is validated;
- what is legacy;
- where new work must go.

## Canonical code

### C++20 backend
`src/cpp/aurora_media/`

Status: ACTIVE.

Contains:
- AuroraMediaContainer
- AuroraStreamProtocol
- AuroraMediaSession

### Python executable reference
`src/python/reference/`

Status: ACTIVE REFERENCE.

Purpose:
- binary reference;
- end-to-end validation;
- interoperability oracle;
- research bridge while codec internals are ported to C++.

## Tests

`tests/cpp/`
`tests/python/`

Status: ACTIVE.

The primary backend workflows have been migrated to these paths.

## Research

`research/audio/`
`research/video/`
`research/backend/`

Status: EXPERIMENTAL/HISTORICAL.

KS and KSV identifiers remain here because they are experiment IDs, not product module names.

## Results

`results/audio/`
`results/video/`
`results/benchmarks/`
`results/backend/`

Status: VALIDATED OUTPUT / ENGINEERING RECORD.

A result does not become an active baseline automatically. Promotion is stated in docs/backend.

## Benchmarks

`benchmarks/`

Status: ACTIVE BENCHMARK INFRASTRUCTURE.

External codecs in this area are comparison targets only.

## Documentation

`docs/`

Status: CANONICAL KNOWLEDGE BASE.

The Technical Master is the authoritative reconstruction of the codec research history.

## Legacy tree

`streaming/`

Status: LEGACY COMPATIBILITY.

Reason retained:
- some historical workflows still reference it;
- research scripts use flat imports;
- deleting it now would break reproducibility.

Rule:
No new production/backend code is to be added there.

## Root KHEPRI experiment files

Root `exp*.py`, `make_exp*_source.py`, and related workflows belong to the wider KHEPRI compressor research lineage.

They are not AURORA Media production modules.

They are retained because the media backend depends historically on EXP-37A and because general KHEPRI development continues separately.

## Cleanup completed

- canonical backend source tree created;
- canonical Python reference tree created;
- C++ tests separated;
- Python tests separated;
- audio research classified;
- video research classified;
- diagnostics classified;
- benchmark harness classified;
- validated result files classified;
- technical master created;
- naming rules created;
- binary format specification created;
- backend roadmap created;
- active backend workflows migrated to canonical paths;
- legacy tree explicitly marked.

## Cleanup intentionally deferred

Do not delete legacy files until:
1. all remaining KS/KSV workflows are migrated;
2. research flat imports are replaced with package-safe imports;
3. canonical benchmark workflow passes;
4. no GitHub workflow references `streaming/` for active code;
5. one final tree audit reports zero active dependencies on duplicate legacy backend files.

This is intentional safety, not unfinished organization.
