# Repository Structure — AURORA Media / KHEPRI

**Canonical branch:** `project/aurora-media`

```text
/
├── README.md
├── engine/
│   └── khepri/
│       ├── source_parts/
│       └── generators/
├── src/
│   ├── cpp/
│   │   └── aurora_media/
│   └── python/
│       └── reference/
├── tests/
│   ├── cpp/
│   └── python/
├── research/
│   ├── audio/
│   │   ├── experiments/
│   │   └── lab/
│   ├── video/
│   │   ├── experiments/
│   │   ├── diagnostics/
│   │   └── lab/
│   └── backend/
├── benchmarks/
│   └── major_codecs/
├── results/
│   ├── audio/
│   ├── video/
│   └── benchmarks/
├── docs/
│   ├── architecture/
│   ├── backend/
│   ├── benchmarks/
│   ├── ip/
│   ├── research/
│   ├── roadmap/
│   └── specs/
└── .github/workflows/
```

## Boundary rules
- `src/` contains production-candidate or executable reference code.
- `engine/khepri/` contains only the minimal backend construction assets used by media.
- `research/` contains experiments, not production modules.
- `results/` contains measured results, never source code.
- `benchmarks/` contains reusable benchmark harnesses.
- `docs/` contains long-lived engineering knowledge.
- general-purpose Silesia/EXP/FAST work belongs to `project/aurora-compressor`.

Historical implementations remain recoverable through Git history instead of duplicate working-tree folders.
