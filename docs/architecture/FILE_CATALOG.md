# AURORA Compressor — catalogo

## Motore
- `engine/source_parts/src_gz_00.b64`
- `engine/source_parts/src_gz_01.b64`
- `engine/source_parts/src_gz_02.b64`

## Ricerca general-purpose
- `research/experiments/` — EXP-23..EXP-50 sweep e varianti sperimentali.
- `research/validation/` — EXP-24B, 26C, 27A, 29B, 30A, 31C, 32A, 33H, 37A, 38A, 39A.
- `research/oracles/` — EXP-41, 42, 43, 45, 47, 49, 50.
- `research/routers/` — EXP-44, 46, 48.
- `research/diagnostics/` — diagnostica EXP-40.
- `research/generators/general/` — make_exp24_source.py ... make_exp39_source.py.

## Ricerca velocità
- `research/generators/speed/` — make_fast*.py e make_speed*.py.
- `research/speed/` — FAST-G ... FAST-Z, SPEED-1/3/4/D e harness A/B.

## Benchmark
- `benchmarks/silesia/bench_silesia.py`
- `benchmarks/competitors/full_compressor_benchmark.py`
- `benchmarks/competitors/exp48_competitor_benchmark.py`

## CI
I workflow sotto `.github/workflows/` mantengono gli ID storici per la riproducibilità ma puntano alle cartelle canoniche sopra.


## Linea ULTRA moderna

- `research/routers/exp59_ultra_text_token.py` — text-token transform origin.
- `research/routers/exp60_ultra_indexed_text_token.py` — indexed tokenization.
- `research/routers/exp61_ultra_confidence_verify.py` — rejected confidence verification.
- `research/routers/exp62_ultra_conservative_grain.py` — conservative grain/context experiment.
- `research/routers/exp63_ultra_cpu_parallel.py` — two-worker CPU parallel checkpoint.
- `research/routers/exp64_ultra_thread_scale.py` — configurable worker scaling.
- `research/routers/exp65_ultra_work_parcels.py` — process-based work parcel scheduler.
- `research/diagnostics/exp60_bottleneck_profile.py` — backend/tokenization timing diagnostic.
- `research/gpu/khepri_gpu_tokenizer.cpp` — OpenCL token-matching prototype with CPU fallback.

These files may reside on their retained experiment branches until explicitly promoted/merged; the catalog records their canonical research role and lineage.
