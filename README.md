# AURORA Compressor / KEPHIR

Questa branch contiene esclusivamente il progetto di compressione file general-purpose basato su KEPHIR.

## Branch canonica

`project/aurora-compressor`

Il progetto codec audio-video è separato nella branch `project/aurora-media`.

## Struttura

```text
engine/
└── source_parts/              sorgente KEPHIR ricostruibile

research/
├── experiments/               esperimenti cronologici EXP
├── validation/                validazione checkpoint promossi
├── oracles/                   oracle / upper-bound research
├── routers/                   structural/adaptive routers
├── diagnostics/               profiling e diagnostica
├── generators/
│   ├── general/               generatori make_exp*
│   └── speed/                 generatori make_fast* / make_speed*
└── speed/                     FAST/SPEED benchmark e A/B

benchmarks/
├── silesia/                   benchmark canonico Silesia
└── competitors/               confronto con compressori esterni

docs/
└── architecture/              struttura e catalogazione

.github/workflows/             CI e riproducibilità
```

## Regola di separazione

AURORA Compressor e AURORA Media condividono la tecnologia KEPHIR e la storia scientifica, ma codice, benchmark, workflow e documentazione specifici dei due prodotti rimangono separati nelle rispettive branch.
