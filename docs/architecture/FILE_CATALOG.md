# AURORA Compressor — catalogo canonico

## Release KEPHIR 1.0

- `release/kephir_final.py` — frontend/integratore KEPHIR 1.0.
- `release/final_qualification.py` — benchmark e qualification finale.
- `release/factory/khepri_factory_v1.json` — Factory Knowledge v1, 79 stati positivi.
- `docs/releases/KEPHIR_1.0.md` — record della baseline qualificata.

## Motore

- `engine/source_parts/src_gz_00.b64`
- `engine/source_parts/src_gz_01.b64`
- `engine/source_parts/src_gz_02.b64`

I source parts ricostruiscono la linea C++ da cui deriva il backend validato.

## Ricerca general-purpose

- `research/experiments/` — linea EXP.
- `research/validation/` — checkpoint retained/promoted.
- `research/oracles/` — oracle e upper-bound.
- `research/routers/` — router strutturali e adaptive grain.
- `research/diagnostics/` — diagnostica e profiling.
- `research/generators/general/` — generatori C++ EXP.
- `research/packaging/exp76_smart_directory_pack.py` — Smart Directory Packing.
- `research/benchmarks/realworld_repo_benchmark.py` — benchmark repository reale.

## Ricerca velocità

- `research/generators/speed/` — generatori FAST/SPEED.
- `research/speed/` — benchmark throughput e same-run A/B.

## Benchmark canonici

- `benchmarks/silesia/`
- `benchmarks/competitors/`
- `release/final_qualification.py`

## Documentazione

- `docs/research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md`
- `docs/architecture/CHECKPOINT_REGISTRY.md`
- `docs/architecture/ADAPTIVE_EXPERIENCE_ENGINE.md`
- `docs/architecture/PROJECT_STRUCTURE.md`
- `docs/architecture/FILE_CATALOG.md`
- `docs/architecture/WORKFLOW_POLICY.md`
- `docs/releases/KEPHIR_1.0.md`
- `docs/INDEX.md`

## CI

I workflow sotto `.github/workflows/` mantengono gli ID storici quando necessari alla riproducibilità. La qualification di prodotto è `KEPHIR 1.0 Final Candidate Qualification`.

## File non canonici / generati

Non devono diventare sorgenti di verità:

- `release/_kephir_engine_runtime.py` — generato a runtime;
- `__pycache__/`, `*.pyc`;
- output benchmark locali;
- archivi `*.kpf` prodotti dai test;
- Local Experience dell'utente;
- file temporanei/sessione.
