# AURORA Compressor Documentation Index

## Start here
1. [Technical & Scientific Master](research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md)
2. [Checkpoint Registry](architecture/CHECKPOINT_REGISTRY.md)
3. [Project Structure](architecture/PROJECT_STRUCTURE.md)
4. [File Catalog](architecture/FILE_CATALOG.md)
5. [Workflow Policy](architecture/WORKFLOW_POLICY.md)

## Research areas
- `research/experiments/` — chronological EXP line.
- `research/validation/` — promoted checkpoint validation.
- `research/oracles/` — oracle/upper-bound experiments.
- `research/routers/` — structural routing.
- `research/diagnostics/` — profiling and analysis.
- `research/speed/` — FAST/SPEED performance research.

## Benchmarks
- `benchmarks/silesia/`
- `benchmarks/competitors/`

## Product split
- general-purpose compressor → `project/aurora-compressor`
- audio/video codec → `project/aurora-media`


## Current ULTRA reference

- **EXP-65** — current practical ULTRA checkpoint.
- Silesia: **63,454,863 B / 29.9402133%**
- encode: **33.34 s / 6.36 MB/s** on a 4-logical-CPU GitHub runner
- SHA: PASS

Additional areas:
- `research/gpu/` — CPU+GPU/OpenCL prototypes.
- `research/diagnostics/` — profiling and bottleneck analysis.
