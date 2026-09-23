# Repository Structure — AURORA Media / KHEPRI

## Goal

The repository is organized to prevent four categories from being mixed:

1. active backend code;
2. executable reference code;
3. experiments;
4. measured results/documentation.

## Canonical tree

```text
/
├── README.md
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
├── source_parts/
└── .github/workflows/
```

## src/cpp/aurora_media

Only backend code intended to evolve toward the production implementation belongs here.

No benchmark-only code, no exploratory variants and no GUI code.

## src/python/reference

This is the executable reference implementation.

Its purpose is correctness and binary compatibility, not speed.

It is the oracle for:
- AUM serialization;
- packet structure;
- index/footer behavior;
- stream framing;
- end-to-end reference behavior.

## research

Everything experimental belongs here.

A research file may be technically successful without being part of the active backend.

Promotion requires documentation.

## results

Only measured results belong here.

Do not store source code in this directory.

Every result file should identify:
- experiment;
- source media;
- backend version;
- relevant parameters;
- compressed bytes;
- reconstruction status;
- decision: promote/reject/retain as control.

## benchmarks

Reusable benchmark harnesses belong here.

External codecs may be used only as references.

## docs

Long-lived technical knowledge belongs here.

The master document is the central historical/scientific record.

## Historical pre-migration tree

The former `streaming/` working tree has been fully removed from the tracked repository after canonical migration.

Its historical content remains recoverable through Git history. Current code must use only the canonical paths above.

Historical KS/KSV workflows may still create temporary runtime output directories whose names contain `streaming/`; these are generated artifacts on CI runners and are not tracked repository source.
