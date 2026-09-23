# Canonical File Map — AURORA Media / KHEPRI

This file defines where every class of artifact belongs. It is the operational map for repository maintenance.

## 1. Canonical production-candidate source

### C++20

`src/cpp/aurora_media/`

- `AuroraCodecInterfaces.h` — stable codec interface contracts.
- `AuroraKhepriBackend.h` — KHEPRI backend adapter boundary.
- `AuroraMediaContainer.{h,cpp}` — native AUM mux/demux/index/CRC implementation.
- `AuroraStreamProtocol.{h,cpp}` — AUS1 framing and stream parser.
- `AuroraMediaSession.{h,cpp}` — timeline, track iteration and recovery-point seek.
- `AuroraMediaError.h` — backend error model.
- `AuroraMediaLimits.h` — hard resource/format limits.

Only code intended to evolve toward production belongs here.

## 2. Canonical executable reference

`src/python/reference/`

- `aurora_media_container.py`
- `aurora_media_codec_bridge.py`
- `aurora_media_converter.py`
- `aurora_media_pipeline.py`
- `aurora_media_session_reference.py`
- `aurora_stream_protocol.py`

Python reference code prioritizes correctness, readability and binary reproducibility over speed.

## 3. Research

### Audio

`research/audio/experiments/` — chronological KS experiments.  
`research/audio/lab/` — reusable experimental frontends and analysis helpers.

### Video

`research/video/experiments/` — chronological KSV experiments.  
`research/video/diagnostics/` — analysis-only tools.  
`research/video/lab/` — reusable motion/residual research modules.

### Backend

`research/backend/` — experiments integrating general KHEPRI checkpoints with media.

Rule: experiment IDs remain in filenames because chronological traceability is valuable here.

## 4. Benchmarks

`benchmarks/major_codecs/`

Benchmark scripts are reusable infrastructure. They must not contain production codec implementation.

## 5. Measured results

`results/audio/`  
`results/video/`  
`results/benchmarks/`

Result filenames use uppercase checkpoint identifiers plus a descriptive suffix.

## 6. Documentation

- `docs/research/AURORA_MEDIA_TECHNICAL_MASTER.md` — scientific/technical master record.
- `docs/architecture/CHECKPOINT_REGISTRY.md` — version decisions.
- `docs/architecture/CANONICAL_FILE_MAP.md` — this file.
- `docs/architecture/WORKFLOW_POLICY.md` — CI/action policy.
- `docs/architecture/REPOSITORY_STRUCTURE.md` — canonical directory tree.
- `docs/architecture/MIGRATION_STATUS.md` — migration state.
- `docs/specs/AURORA_MEDIA_FORMAT_V01.md` — AUM binary format baseline.
- `docs/backend/*` — active backend baseline descriptions.
- `docs/benchmarks/BENCHMARK_METHOD.md` — benchmark methodology.
- `docs/ip/IP_REGISTER.md` — standard/background/candidate-IP classification.
- `docs/roadmap/BACKEND_ROADMAP.md` — forward engineering roadmap.

## 7. Legacy compatibility tree

`streaming/` is not a canonical development location.

It is retained only for historical scripts/imports that have not yet been migrated.

Exact byte-for-byte duplicates of canonical files are removed when verified.

Legacy files that differ are preserved until their historical role is classified or their workflow/import dependency is removed.

No new production file may be added to `streaming/`.

## 8. General KHEPRI root files

Root files such as `exp23_*.py`, `make_exp*_source.py` and `bench_silesia.py` belong to the general KHEPRI research lineage inherited from `main`.

They remain at the root temporarily because numerous reproducibility workflows reference those paths.

They are not AURORA Media production modules.

Future cleanup should migrate them as one coordinated operation rather than piecemeal renames that break historical workflows.

## 9. Naming standard

### Production C++
PascalCase, role-based.

### Python reference
lowercase snake_case, role-based.

### Research experiments
chronological ID + descriptive snake_case.

### Results
UPPERCASE_CHECKPOINT + descriptive uppercase suffix + `.md`.

### Canonical documentation
UPPERCASE descriptive names.

### Forbidden new-name patterns

- `new_*.py`
- `final_*.py`
- `final2_*.py`
- `test123.py`
- `latest.py`
- `results.json` without experiment identity
- duplicate version identifiers for unrelated experiments.

## 10. Current duplicate-removal record

Verified exact legacy duplicates removed from `streaming/`:

- `cpp/AuroraMediaSession.cpp`
- `cpp/AuroraMediaSession.h`
- `aurora_media_container_v01.py`
- `aurora_stream_protocol_v01.py`
- `KSV05_RESULTS.md`
- `MAJOR_CODEC_BENCHMARK_RESULTS.md`
- `IP_REGISTER.md`

Their canonical copies remain in `src/`, `results/` or `docs/`.
