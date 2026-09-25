# AURORA Compressor — struttura canonica

**Canonical branch:** `project/aurora-compressor`

## Confine del progetto

Questa linea contiene solo compressione general-purpose di file e archivi.

Audio, video, container AUM, protocollo AUS1 e streaming appartengono a `project/aurora-media`.

## Struttura

~~~text
/
├── README.md
├── engine/
│   └── source_parts/
├── release/
│   ├── kephir_final.py
│   ├── final_qualification.py
│   └── factory/
│       └── khepri_factory_v1.json
├── research/
│   ├── experiments/
│   ├── validation/
│   ├── oracles/
│   ├── routers/
│   ├── diagnostics/
│   ├── generators/
│   │   ├── general/
│   │   └── speed/
│   ├── speed/
│   ├── packaging/
│   └── benchmarks/
├── benchmarks/
│   ├── silesia/
│   └── competitors/
├── docs/
│   ├── architecture/
│   ├── releases/
│   └── research/
└── .github/workflows/
~~~

## Ruoli delle aree

- `engine/source_parts/` — ricostruzione del backend C++ storico.
- `release/` — superficie integrata qualificabile; non è area di esperimenti.
- `release/factory/` — Factory Knowledge read-only distribuita con il prodotto.
- `research/experiments/` — esperimenti cronologici.
- `research/validation/` — validazioni di checkpoint.
- `research/oracles/` — upper bound non production-ready.
- `research/routers/` — router strutturali/adattivi.
- `research/diagnostics/` — profiling e diagnostica.
- `research/generators/` — generatori delle linee EXP/FAST.
- `research/speed/` — throughput research.
- `research/packaging/` — Smart Directory Packing e futuri container experiments.
- `research/benchmarks/` — benchmark real-world/R&D.
- `benchmarks/` — harness benchmark canonici e competitor.
- `docs/releases/` — baseline e qualification record.

## Regole

1. Nessun nuovo script di ricerca va nella root.
2. Gli ID storici EXP/FAST restano nei nomi dei file.
3. I risultati promossi devono essere documentati.
4. `release/` contiene solo componenti integrati destinati a qualification/release.
5. Factory e Local Experience restano separate.
6. Il decoder non dipende da Factory/Local Experience.
7. I file runtime, cache, output benchmark e knowledge locali non vanno versionati.
8. Il lavoro media non entra in questa branch.
9. Il commit qualificato di una release non viene riscritto: ogni modifica successiva richiede nuova qualification.
