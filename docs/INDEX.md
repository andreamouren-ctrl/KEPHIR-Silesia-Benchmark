# AURORA Compressor Documentation Index

## KEPHIR 1.0
1. [KEPHIR 1.0 Release Baseline](releases/KEPHIR_1.0.md)
2. [Technical & Scientific Master](research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md)
3. [Checkpoint Registry](architecture/CHECKPOINT_REGISTRY.md)
4. [Adaptive Experience Engine](architecture/ADAPTIVE_EXPERIENCE_ENGINE.md)
5. [Project Structure](architecture/PROJECT_STRUCTURE.md)
6. [File Catalog](architecture/FILE_CATALOG.md)
7. [Workflow Policy](architecture/WORKFLOW_POLICY.md)

## Release status

- Qualified engine commit: `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`
- Qualification run: `36151845469`
- Result: **SUCCESS**
- Roundtrip: **FINAL_SHA_ALL_PASS**
- Factory Knowledge v1: **79 positive states**

## Research areas

- `research/experiments/` — chronological EXP line.
- `research/validation/` — promoted checkpoint validation.
- `research/oracles/` — oracle / upper-bound research.
- `research/routers/` — structural and adaptive routers.
- `research/diagnostics/` — profiling and diagnostics.
- `research/speed/` — FAST/SPEED research.
- `research/packaging/` — archive/directory packing research.
- `research/benchmarks/` — real-world qualification harnesses.

## Benchmarks

- `benchmarks/silesia/`
- `benchmarks/competitors/`
- final qualification: `release/final_qualification.py`

## Product split

- general-purpose compressor → `project/aurora-compressor`
- audio/video codec → `project/aurora-media`
