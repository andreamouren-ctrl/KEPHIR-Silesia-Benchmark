# AURORA Compressor / KHEPRI

KHEPRI è il motore lossless general-purpose di AURORA Compressor.

## Stato corrente

**Baseline ufficiale:** KEPHIR 1.0  
**Commit qualificato del motore:** `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`  
**Qualification run:** `36151845469` — **SUCCESS**  
**Lossless validation:** **FINAL_SHA_ALL_PASS**

Il codice qualificato mantiene intenzionalmente il marker `1.0.0-rc1`: il commit sopra è il riferimento byte-for-byte validato. La promozione a baseline 1.0 è documentale; eventuali modifiche al codice o al version string devono essere riqualificate.

## Risultati qualificati

### Silesia canonico — 211,938,580 B

| Profilo | Archive bytes | Ratio | Compress | Decompress | SHA |
|---|---:|---:|---:|---:|:---:|
| KEPHIR 1.0 cold | 62,953,321 | 29.704% | 96.050 s | 13.645 s | PASS |
| KEPHIR 1.0 Factory | 62,958,288 | 29.706% | 75.057 s | 13.629 s | PASS |

La Factory Knowledge riduce il tempo di compressione senza cambiare il decoder e senza rendere l'archivio dipendente dal database di esperienza.

### Repository reale qualificato — 242 file / 759,128 B

| Profilo | Archive bytes | Ratio | Compress | Decompress | SHA |
|---|---:|---:|---:|---:|:---:|
| KEPHIR 1.0 cold | 117,523 | 15.481% | 1.703 s | 0.078 s | PASS |
| KEPHIR 1.0 Factory | 117,523 | 15.481% | 0.705 s | 0.080 s | PASS |

## Architettura 1.0

La baseline integra:

- backend KEPHIR lossless;
- adaptive grain selection;
- Word-XOR predittivo/lazy;
- cost-aware parcel scheduling;
- multiprocessing encoder-side;
- Smart Directory Packing content-first;
- Factory Knowledge read-only;
- Local Experience persistente opzionale;
- decoder indipendente dai database di apprendimento;
- manifest compatto e ricostruzione directory;
- verifica roundtrip esatta;
- protezione base da path traversal in estrazione.

## Struttura canonica

~~~text
engine/
└── source_parts/

release/
├── kephir_final.py
├── final_qualification.py
└── factory/
    └── khepri_factory_v1.json

research/
├── experiments/
├── validation/
├── oracles/
├── routers/
├── diagnostics/
├── generators/
├── speed/
├── packaging/
└── benchmarks/

benchmarks/
├── silesia/
└── competitors/

docs/
├── architecture/
├── releases/
└── research/

.github/workflows/
~~~

## Documentazione

- `docs/releases/KEPHIR_1.0.md` — baseline 1.0 e risultati finali.
- `docs/research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md` — master tecnico/scientifico.
- `docs/architecture/CHECKPOINT_REGISTRY.md` — registro checkpoint.
- `docs/architecture/ADAPTIVE_EXPERIENCE_ENGINE.md` — Factory/Local/Session Experience.
- `docs/architecture/PROJECT_STRUCTURE.md` — struttura canonica.
- `docs/architecture/FILE_CATALOG.md` — catalogo delle aree.
- `docs/INDEX.md` — indice documentazione.

## Branch

- General-purpose: `project/aurora-compressor`
- Media codec: `project/aurora-media`
- Release candidate qualificata: `release/kephir-1.0-final-candidate`

AURORA Compressor e AURORA Media possono condividere concetti KEPHIR, ma benchmark, frontend, container e ricerca specifica restano separati.
