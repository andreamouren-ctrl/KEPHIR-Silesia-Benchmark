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
- `docs/architecture/ADAPTIVE_EXPERIENCE_ENGINE.md` — memoria adattiva, knowledge base factory e apprendimento persistente.
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


## Stato ULTRA corrente

Current practical checkpoint:

```text
EXP-66
Silesia raw:        211,938,580 B
Compressed:          63,454,863 B
Ratio:               29.9402133%
Encode:              25.97 s
Encode throughput:    8.16 MB/s
SHA:                 PASS
Runner:              4 logical CPUs
```

Recent architecture work:
- conservative grain routing to preserve context;
- reversible indexed text tokenization;
- process-based work parcels for multicore scaling;
- OpenCL CPU+GPU token-matching prototype with exact CPU fallback;
- explicit profiling of backend calls, tokenization and scheduler overhead.
- Adaptive Experience Engine con knowledge base factory pre-addestrata e apprendimento locale persistente.

GPU performance is not yet claimed: hosted CI validated build/reversibility but used CPU fallback.
