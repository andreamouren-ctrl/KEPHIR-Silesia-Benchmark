# KEPHIR 2 / AUR Container 2 — Integration Freeze Manifest

**Freeze:** Integration RC1  
**Branch:** `release/kephir-2.0-aur2-integration-rc1`  
**Date:** 2026-10-05  
**Purpose:** stable engine/container snapshot for final AURORA Compressor integration and installer work.

## Frozen public versions

- KEPHIR engine: `2.0.0-rc1`
- KEPHIR C API: `1`
- AUR container: `2.0`
- Native K75 backend stream format: `1`
- Legacy read compatibility: KPF1

## Freeze policy

KEPHIR 2 / AUR2 is now in **feature freeze**.

Allowed until AURORA Compressor ships:

1. bug fixes required by real application integration;
2. ABI-compatible API additions that are demonstrably necessary for AURORA;
3. installer/build/package fixes;
4. correctness, portability, security and data-loss fixes;
5. documentation corrections.

Not allowed in KEPHIR 2 / AUR2 after this freeze:

- new compression experiments;
- new grain/context algorithms;
- new transform families;
- bitstream redesign;
- container redesign;
- breaking C ABI changes;
- enum renumbering;
- reusing published capability/feature bits;
- research-only parameters in the public API.

All new compression/container research moves to **KEPHIR 3 / AUR3** after AURORA Compressor and its installer are complete.

## Frozen architecture

```text
AURORA Compressor
    |
    v
CompressionService / Kephir2Backend
    |
    v
KEPHIR C ABI v1
    |
    +-- Native KEPHIR2 / K75
    |
    +-- AUR Container v2 writer/reader
    |
    +-- KPF1 legacy reader
```

AURORA must not depend on K75 internals, experimental branch names, research scripts or router implementation details.

## Public C ABI included in RC1

- `kephir2_api_version`
- `kephir2_engine_version`
- `kephir2_create`
- `kephir2_destroy`
- `kephir2_options_init_v1`
- `kephir2_get_capabilities`
- `kephir2_compress`
- `kephir2_extract`
- `kephir2_inspect`
- `kephir2_list_entries`
- `kephir2_test_archive`
- `kephir2_extract_selected`
- `kephir2_status_name`

Public profiles remain:

- `AUTO`
- `FAST`
- `BALANCED`
- `MAX`

`AUTO` is the recommended integration default and enables the qualified adaptive-context production policy.

## AUR2 capabilities frozen for integration

Implemented and qualified:

- fixed 64-byte versioned header;
- TLV section framing;
- FILE_TABLE;
- codec descriptor;
- block/stream table;
- DATA section;
- per-stream CRC32 integrity;
- SEEK_INDEX / TOC;
- FTR1 footer integrity;
- active `toc_offset` / `footer_offset` validation;
- file archives;
- directory archives;
- SMART / FLAT packing;
- empty files;
- empty directories;
- UTF-8 relative paths;
- path traversal rejection;
- basic portable mtime and permission metadata;
- inspect/list without materializing DATA;
- deep archive test;
- selective extraction;
- file-backed bounded-by-stream extraction;
- file-backed finalization of new archives;
- transactional extraction staging/rollback;
- monotonic multi-stream progress;
- cooperative cancellation;
- KPF1 legacy read fallback.

Not part of AUR2 RC1:

- encryption;
- recovery/parity;
- ACL preservation;
- Windows Alternate Data Streams;
- symlink preservation;
- fully streaming K75 encode/decode.

These are future-generation work unless a critical AURORA requirement forces an ABI-compatible addition.

## Compression-core scope frozen in KEPHIR2

RC1 includes the production-safe adaptive-context lineage validated before the freeze:

- bounded content sampling;
- 512 KiB / 4 MiB / 8 MiB context policy;
- structural-volatility safety gate;
- long-context AUTO layout bootstrap;
- NativeK75 self-describing decode parameters.

The following remain **research only and are intentionally NOT promoted into RC1**:

- EXP-118B Python bounded grain-probe router;
- EXP-120A mixed parent-grain oracle;
- `grain2` experiment;
- mixed-grain per-superchunk format changes.

Those results are preserved for KEPHIR3 design.

## RC1 integration SDK

The Windows x64 RC1 integration artifact is assembled from the frozen public surface only:

```text
kephir2-sdk-2.0.0-rc1-windows-x64/
  include/kephir2/kephir2_c.h
  bin/kephir2_api.dll
  lib/kephir2_api.lib
  cmake/Kephir2Config.cmake
  docs/
  VERSION
  SHA256SUMS
```

`Kephir2Config.cmake` exposes the imported target `Kephir2::kephir2`. The package is validated by a separate CMake consumer that calls the public C ABI and checks API/runtime versioning. The installed AURORA application has no Python runtime dependency; Python remains a repository source-build/generation dependency only.

## Already qualified AUR2 checkpoints

- RC1 SDK/package consumer gate: run `37271671809` — PASS Linux/Windows; Windows SDK staging + external CMake consumer PASS.
- Final AUR2 Linux/Windows gate: run `37238651446` — PASS.
- Scale qualification: run `37238274255` — PASS.
- Transactional extraction: run `37237322025` — PASS Linux/Windows.
- Multi-stream progress: run `37237913015` — PASS Linux/Windows.
- Historical KEPHIR core regression/Silesia workflow: run `36916395796` — PASS.

Scale qualification reference:

- 16 MiB fixture: encode ~29.893 MiB/s, decode ~280.917 MiB/s.
- 64 MiB fixture: encode ~32.668 MiB/s, decode ~277.182 MiB/s.
- 64 MiB peak RSS: ~106.15 MiB encode / ~43.66 MiB decode.
- exact SHA round-trip: PASS.

These scale numbers qualify the AUR2 I/O path; they are not a Silesia competitor claim.

## Compatibility rules during AURORA integration

1. `KEPHIR2_API_VERSION` stays `1`.
2. Existing enum numeric values never change.
3. Existing struct field order never changes.
4. Existing function semantics are not broken.
5. New struct versions/functions may be added only when needed by AURORA.
6. AUR2 major remains `2`.
7. Published feature bits and section IDs never change meaning.
8. New optional AUR2 extensions must be ignorable by older AUR2 readers unless explicitly required.
9. KPF1 read compatibility is retained for the transition.
10. KEPHIR1/AUR1 compatibility in AURORA remains an application/legacy-reader concern until migration is complete.

## Promotion path

```text
RC1 freeze
  -> integrate into AURORA Compressor
  -> fix only integration defects / required API gaps
  -> complete application
  -> complete installer
  -> final integration qualification
  -> freeze KEPHIR 2.0 / AUR 2.0 release
  -> start KEPHIR 3 / AUR 3 R&D
```

## Source of truth

During application integration, use only:

- this release branch;
- `src/kephir2/include/kephir2/kephir2_c.h`;
- `src/kephir2/cmake/Kephir2Config.cmake`;
- `docs/architecture/AUR2_CONTAINER_FORMAT.md`;
- `docs/architecture/AUR2_IMPLEMENTATION_STATUS.md`;
- `docs/integration/AURORA_KEPHIR2_INTEGRATION_CHECKLIST.md`;
- the generated RC1 SDK artifact.

Do not integrate directly from `research/*` branches.
