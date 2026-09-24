# Canonical File Map — AURORA Media / KHEPRI

**Branch:** `project/aurora-media`

## Production C++20
`src/cpp/aurora_media/`

Contains the production-candidate media backend, AUM container, AUS1 stream protocol, session layer, video motion/residual code, GPU compute path and public codec interfaces.

## Python reference
`src/python/reference/`

Executable reference implementation for binary compatibility, container behavior, streaming framing and end-to-end validation.

## Shared KHEPRI backend kit
`engine/khepri/`

Only the minimal general KHEPRI assets required to rebuild the media backend are retained here:

- `source_parts/`
- `generators/make_exp26_source.py`
- `generators/make_exp27_source.py`
- `generators/make_exp31_source.py`
- `generators/make_exp33_source.py`
- `generators/make_exp37_source.py`

General-purpose EXP/FAST/Silesia research does not belong in this branch. It is maintained on `project/aurora-compressor`.

## Research
- `research/audio/experiments/`
- `research/audio/lab/`
- `research/video/experiments/`
- `research/video/diagnostics/`
- `research/video/lab/`
- `research/backend/`

## Tests
- `tests/cpp/`
- `tests/python/`

## Benchmarks
`benchmarks/major_codecs/`

## Results
- `results/audio/`
- `results/video/`
- `results/benchmarks/`

## Documentation
- `docs/research/AURORA_MEDIA_TECHNICAL_MASTER.md`
- `docs/architecture/CHECKPOINT_REGISTRY.md`
- `docs/architecture/REPOSITORY_STRUCTURE.md`
- `docs/architecture/MIGRATION_STATUS.md`
- `docs/architecture/WORKFLOW_POLICY.md`
- `docs/specs/AURORA_MEDIA_FORMAT_V01.md`
- `docs/backend/`
- `docs/benchmarks/`
- `docs/ip/`
- `docs/roadmap/`

## Historical policy
The former `streaming/` tree and inherited general-purpose root research were removed from the working tree. Git history is the archive for those versions. No duplicate compatibility source tree should be recreated.
