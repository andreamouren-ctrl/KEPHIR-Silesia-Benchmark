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

## 7. Historical implementation policy

The former `streaming/` source tree has been removed.

Historical versions are preserved by Git history rather than by duplicate files in the working tree.

A historical experiment that still needs executable reproduction must point to its canonical file under `research/`, `src/`, `tests/` or `benchmarks/`.

Do not create a second compatibility source tree.

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

## 10. Migration result

The duplicate-removal/migration pass is complete for AURORA Media.

Verified duplicate and superseded legacy files were removed from the tracked tree after their canonical replacements were identified.

Historical pre-migration content remains accessible through Git history.
