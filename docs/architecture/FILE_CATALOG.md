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
