# Canonical Path Migration Status

## Migrated and active

- C++20 container backend → `src/cpp/aurora_media/`
- C++20 stream backend → `src/cpp/aurora_media/`
- C++20 media session → `src/cpp/aurora_media/`
- Python AUM reference → `src/python/reference/`
- Python A/V pipeline reference → `src/python/reference/`
- Python stream reference → `src/python/reference/`
- C++/Python interoperability tests → `tests/`
- native end-to-end backend tests → `tests/`
- major codec benchmark canonical copy → `benchmarks/`
- KSV-05 canonical research copy → `research/video/experiments/`
- IP register → `docs/ip/`
- validated KS/KSV result records → `results/`
- scientific/technical master → `docs/research/`
- checkpoint registry → `docs/architecture/`
- canonical file map → `docs/architecture/`
- workflow policy → `docs/architecture/`

## Exact legacy duplicates removed

The following byte-identical duplicates were safely deleted from `streaming/` because canonical copies already exist:

- `streaming/cpp/AuroraMediaSession.cpp`
- `streaming/cpp/AuroraMediaSession.h`
- `streaming/aurora_media_container_v01.py`
- `streaming/aurora_stream_protocol_v01.py`
- `streaming/KSV05_RESULTS.md`
- `streaming/MAJOR_CODEC_BENCHMARK_RESULTS.md`
- `streaming/IP_REGISTER.md`

## Still legacy-dependent

Older KS/KSV experiment workflows and flat Python experimental imports.

Some legacy C++ container/stream files differ from the canonical backend and are intentionally retained as historical versions rather than deleted blindly.

## Root general-KHEPRI files

Root `exp*.py`, `make_exp*_source.py` and related workflow files belong to the wider general-purpose KHEPRI lineage.

They remain temporarily because historical/reproducibility workflows reference those exact paths.

A future root migration should be one coordinated change, not piecemeal renaming.

## Rule for new work

- production/backend C++ → `src/cpp/aurora_media/`
- Python binary/reference model → `src/python/reference/`
- experiments → `research/`
- benchmark harnesses → `benchmarks/`
- measured results → `results/`
- long-lived documentation → `docs/`

`streaming/` is read-only legacy compatibility and must receive no new production code.

## Remaining cleanup gate

The legacy tree can be removed only after:

1. all active KS/KSV workflow imports use canonical paths;
2. research flat imports are package-safe;
3. canonical backend/benchmark workflows pass after migration;
4. no active workflow depends on duplicate legacy implementation files;
5. one final tree audit reports no live dependency on `streaming/`.
