# Legacy Compatibility Notice

The `streaming/` directory is the historical working tree used during early AURORA Media research.

It is retained temporarily because existing experiments and GitHub Actions workflows still reference these paths.

Canonical locations are now:
- backend C++: `src/cpp/aurora_media/`
- Python reference: `src/python/reference/`
- experiments: `research/`
- results: `results/`
- benchmarks: `benchmarks/`
- documentation: `docs/`

Do not add new production/backend files to `streaming/`.

Deletion/migration of these legacy files must happen only after all imports and workflows use the canonical tree and pass regression tests.
