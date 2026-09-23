# AURORA Media / KHEPRI Codec

Research and backend repository for the AURORA Media lossless audio/video codec and its KHEPRI compression backend.

## Current validated baseline

- Media backend: **KHEPRI EXP-37A PREDICTIVE-DUAL-MATCH**
- Audio: **KMRL FULL256 + TAIL16**
- Video: **TEMP / MC8R4 adaptive routing, 20-frame horizon**
- Container: **AUM v0.1**
- Stream framing: **AUS1 v0.1**
- Python executable reference: validated
- C++20 container/session/stream backend: validated
- Python ↔ C++ binary interoperability: validated
- Current path: **lossless / bit-exact**

## Repository map

- `src/cpp/aurora_media/` — canonical C++20 backend
- `src/python/reference/` — executable binary-format/reference model
- `tests/` — interoperability, corruption and end-to-end tests
- `research/audio/` — audio experiments and lab code
- `research/video/` — video experiments and lab code
- `research/backend/` — KHEPRI backend integration experiments
- `benchmarks/` — reproducible comparison harnesses
- `results/` — validated measured results
- `docs/` — architecture, format, scientific history, IP and roadmap
- `streaming/` — legacy compatibility tree retained temporarily while workflows/imports are migrated
- `source_parts/` — historical/reconstruction assets for KHEPRI research sources

## Canonical documentation

Start here:

1. `docs/research/AURORA_MEDIA_TECHNICAL_MASTER.md`
2. `docs/architecture/REPOSITORY_STRUCTURE.md`
3. `docs/specs/AURORA_MEDIA_FORMAT_V01.md`
4. `docs/benchmarks/BENCHMARK_METHOD.md`
5. `docs/ip/IP_REGISTER.md`
6. `docs/roadmap/BACKEND_ROADMAP.md`

## Development rule

Production/backend code and research code are separated.

An experiment becomes part of the active baseline only after:
- successful encode/decode;
- bit-exact validation for lossless modes;
- measured improvement or required architectural value;
- result documentation;
- explicit promotion in backend documentation.

No GUI work belongs in this branch's backend core.
