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

## streaming legacy tree

The historical `streaming/` directory is temporarily retained because:
- existing workflows reference it;
- Python imports reference neighboring files;
- historical commit links and experiment reproduction still use those paths.

It is not the canonical location for new files.

New backend work goes into `src/`.
New experiments go into `research/`.
New results go into `results/`.

Legacy deletion should happen only after workflow/import migration tests pass.
