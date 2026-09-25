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
- `research/routers/exp66_ultra_cost_aware.py` — current practical cost-aware LPT scheduler.
- `research/routers/exp67_ultra_selective_psg.py` — retained selective complementary PSG verification.
- `research/routers/exp68_ultra_psg_gate.py` — retained BASE-gated PSG verification.
- `research/routers/exp69_ultra_wordxor.py` — rejected Word-XOR entropy-router experiment.
- `research/routers/exp70_adaptive_experience.py` — first online Adaptive Experience learner; six-corpus, three-epoch validation.
- `research/diagnostics/exp60_bottleneck_profile.py` — backend/tokenization timing diagnostic.
- `research/gpu/khepri_gpu_tokenizer.cpp` — OpenCL token-matching prototype with CPU fallback.

These files may reside on their retained experiment branches until explicitly promoted/merged; the catalog records their canonical research role and lineage.


## Adaptive Experience documentation

- `docs/architecture/ADAPTIVE_EXPERIENCE_ENGINE.md` — canonical specification for Factory Knowledge, local persistence, session learning, utility scoring, exploration, confidence/decay, compatibility and privacy.
- `docs/research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md` — measured EXP-70 evidence and research lineage.
- `docs/architecture/CHECKPOINT_REGISTRY.md` — formal status of EXP-66→70.

## Adaptive Experience artifacts (planned production roles)

The following are conceptual production artifacts; their final paths/extension remain unfrozen:
- Factory knowledge store — shipped read-only with AURORA/KEPHIR;
- Local experience store — writable per-installation overlay;
- Session state — temporary/in-memory learning state;
- knowledge schema/compatibility metadata;
- factory-training/export tool generated from approved benchmark runs.

These roles are canonical even if implementation filenames change before format freeze.
