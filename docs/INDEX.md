# AURORA Compressor Documentation Index

## KEPHIR 1.0
1. [KEPHIR 1.0 Release Baseline](releases/KEPHIR_1.0.md)
2. [Technical & Scientific Master](research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md)
3. [Checkpoint Registry](architecture/CHECKPOINT_REGISTRY.md)
4. [Adaptive Experience Engine](architecture/ADAPTIVE_EXPERIENCE_ENGINE.md)
5. [Project Structure](architecture/PROJECT_STRUCTURE.md)
6. [File Catalog](architecture/FILE_CATALOG.md)
7. [Workflow Policy](architecture/WORKFLOW_POLICY.md)
8. [AURORA / KEPHIR Final Integration Specification](architecture/AURORA_KEPHIR_FINAL_INTEGRATION_SPEC.md)

## Release status

- Qualified engine commit: `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`
- Qualification run: `36151845469`
- Result: **SUCCESS**
- Roundtrip: **FINAL_SHA_ALL_PASS**
- Factory Knowledge v1: **79 positive states**

## Research mantenuta

- `research/routers/` — linea promossa EXP-66 / EXP-72…75.
- `research/packaging/` — Smart Directory Packing EXP-76.
- `research/benchmarks/` — benchmark real-world ancora utile.

Gli esperimenti superseded non sono più mantenuti nel working tree: restano recuperabili dalla cronologia Git e i risultati consolidati sono nel Technical Master e nel Checkpoint Registry.

## Benchmarks

- `benchmarks/silesia/`
- `benchmarks/competitors/`
- final qualification: `release/final_qualification.py`

## Product split

- general-purpose compressor → `project/aurora-compressor`
- audio/video codec → `project/aurora-media`
