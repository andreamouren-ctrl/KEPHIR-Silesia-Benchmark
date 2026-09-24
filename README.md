# AURORA Media / KEPHIR

Questa branch contiene esclusivamente il progetto codec audio-video AURORA Media basato sul backend KEPHIR.

## Branch canonica

`project/aurora-media`

Il compressore general-purpose di file e archivi è separato nella branch `project/aurora-compressor`.

## Struttura principale

```text
engine/
└── khepri/
    ├── source_parts/          frammenti sorgente backend
    └── generators/            generatori minimi EXP necessari al codec

src/
├── cpp/aurora_media/          backend C++20, container, stream, video/GPU
└── python/reference/          reference implementation

research/
├── audio/
├── video/
└── backend/

tests/
├── cpp/
└── python/

benchmarks/
└── major_codecs/

results/
├── audio/
├── video/
└── benchmarks/

docs/                         specifiche, architettura, master tecnico, roadmap
.github/workflows/            CI media, KS/KSV, GPU e benchmark
```

## Regola di separazione

La branch media conserva solo il sottoinsieme KEPHIR necessario a costruire e testare il codec. La ricerca general-purpose Silesia/EXP/FAST appartiene a `project/aurora-compressor`.
