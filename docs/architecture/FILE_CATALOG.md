# AURORA Compressor — catalogo canonico

## Release KEPHIR 1.0

- `release/kephir_final.py` — frontend/integratore KEPHIR 1.0.
- `release/final_qualification.py` — benchmark e qualification finale.
- `release/factory/khepri_factory_v1.json` — Factory Knowledge v1.
- `docs/releases/KEPHIR_1.0.md` — record della baseline qualificata.

## Motore

- `engine/source_parts/src_gz_00.b64`
- `engine/source_parts/src_gz_01.b64`
- `engine/source_parts/src_gz_02.b64`

I source parts ricostruiscono la linea C++ da cui deriva il backend validato.

## Ricerca mantenuta

- `research/routers/exp66_ultra_cost_aware.py` — cost-aware routing promosso.
- `research/routers/exp72_adaptive_grain.py` — adaptive grain.
- `research/routers/exp73_grain_wordxor.py` — grain + Word-XOR.
- `research/routers/exp74_predictive_wordxor.py` — Word-XOR predittivo.
- `research/routers/exp75_lazy_wx_fingerprint.py` — lazy Word-XOR / fingerprint.
- `research/packaging/exp76_smart_directory_pack.py` — Smart Directory Packing.
- `research/benchmarks/realworld_repo_benchmark.py` — benchmark repository reale.

Gli script EXP/FAST/SPEED superseded sono rimossi dal working tree; restano nella cronologia Git e i risultati consolidati sono nei documenti tecnici.

## Benchmark canonici

- `benchmarks/silesia/bench_silesia.py`
- `benchmarks/competitors/full_compressor_benchmark.py`
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

## CI mantenuta

Il working tree conserva soltanto workflow ancora utili per qualification, benchmark canonici e la linea di ricerca promossa. La qualification di prodotto è `KEPHIR 1.0 Final Candidate Qualification`.

## File non canonici / generati

Non devono diventare sorgenti di verità:

- `release/_kephir_engine_runtime.py` — generato a runtime;
- `__pycache__/`, `*.pyc`;
- output benchmark locali;
- archivi `*.kpf` prodotti dai test;
- Local Experience dell'utente;
- file temporanei/sessione;
- frammenti di sorgente temporanei nella root.
