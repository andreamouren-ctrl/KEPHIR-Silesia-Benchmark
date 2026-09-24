# AURORA Compressor / KHEPRI

Questa branch contiene esclusivamente il progetto di compressione file general-purpose basato su KHEPRI.

## Branch canonica

`project/aurora-compressor`

Il progetto codec audio-video è separato nella branch `project/aurora-media`.

## Documentazione principale

- `docs/research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md` — master tecnico/scientifico completo.
- `docs/architecture/CHECKPOINT_REGISTRY.md` — checkpoint promossi, retained e rejected.
- `docs/architecture/PROJECT_STRUCTURE.md` — struttura canonica.
- `docs/architecture/FILE_CATALOG.md` — catalogo delle aree.
- `docs/architecture/WORKFLOW_POLICY.md` — regole CI e riproducibilità.
- `docs/INDEX.md` — indice della documentazione.

## Struttura

```text
engine/
└── source_parts/

research/
├── experiments/
├── validation/
├── oracles/
├── routers/
├── diagnostics/
├── generators/
│   ├── general/
│   └── speed/
└── speed/

benchmarks/
├── silesia/
└── competitors/

docs/
├── architecture/
└── research/

.github/workflows/
```

## Regola di separazione

AURORA Compressor e AURORA Media condividono la tecnologia KHEPRI e la storia scientifica, ma codice, benchmark, workflow e documentazione specifici dei due prodotti rimangono separati nelle rispettive branch.
