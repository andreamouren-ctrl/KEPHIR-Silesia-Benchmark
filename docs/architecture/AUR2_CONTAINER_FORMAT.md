# AUR Container v2.0 — Binary Core Specification

**Status:** implementation-qualified / pre-freeze  
**Branch:** `development/aur2-container-core`  
**Target:** `development/kephir-2-core`  
**Snapshot:** 2026-10-04  
**Scope:** stable product-container framing above the KEPHIR codec payload.

> This document describes the format actually implemented by the current AUR2 core. The byte-level registry is not externally frozen until the final release-candidate compatibility review, but section IDs and published feature bits below must already be treated as append-only.

## Design boundary

`.aur` is the AURORA product container. KEPHIR is the compression codec/backend carried by that container. AUR2 does not expose research experiment identifiers and does not require a decoder to reproduce encoder-side routing, probe, grain or transform decisions.

The outer container owns product-level structure: entries, streams, offsets, integrity, indexing and extensible metadata. Decoder-required KEPHIR details remain in the codec descriptor/payload.

## Byte order and primitive encoding

All fixed-width integers are little-endian.

The `FILE_TABLE` uses the existing KEPHIR unsigned varint encoding. Signed modification time is ZigZag-encoded and then stored as an unsigned varint.

No C/C++ struct is serialized by dumping native memory; fields are emitted explicitly to avoid ABI, padding and endianness dependencies.

## Fixed header

The v2.0 fixed header is exactly **64 bytes**.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | magic `AUR2\r\n\x1A\n` |
| 8 | 2 | container major |
| 10 | 2 | container minor |
| 12 | 4 | header size |
| 16 | 8 | feature flags |
| 24 | 8 | archive id |
| 32 | 8 | logical size |
| 40 | 8 | TOC / SEEK_INDEX offset |
| 48 | 8 | FTR1 footer section offset |
| 56 | 4 | header CRC32 |
| 60 | 4 | reserved, must be zero |

For v2.0 the header CRC32 covers bytes `[0,56)`. The CRC field itself and the reserved word are not included.

Current rules:

- `container_major == 2`;
- `container_minor == 0` for the current writer;
- `header_size == 64`;
- `reserved == 0`;
- a legacy/development AUR2 without `SEEK_INDEX` may have `toc_offset == 64` as the historical section-scan start;
- a current indexed AUR2 has `SEEK_INDEX` as the first section and `toc_offset == header_size == 64`;
- when `FooterIntegrity` is present, `footer_offset` points exactly to the final `FTR1` section header;
- legacy AUR2 without `FTR1` may have `footer_offset == 0`;
- inconsistent feature/section/offset combinations are rejected.

## TLV section framing

Every section uses a 16-byte header:

| Size | Field |
|---:|---|
| 4 | section type |
| 4 | section flags |
| 8 | payload length |

Section flags:

- bit 0: `IGNORABLE`;
- bit 1: `REQUIRED`.

A section cannot be both `REQUIRED` and `IGNORABLE`. Unknown sections are accepted only when `IGNORABLE` is set; unknown non-ignorable/required sections are rejected.

## Section type registry

| Type | Name | Current role |
|---:|---|---|
| `0x0001` | `FILE_TABLE` | file/directory entries and metadata |
| `0x0002` | `CODEC_DESCRIPTOR` | KEPHIR codec and decoder-binding data |
| `0x0003` | `BLOCK_TABLE` | logical compressed-stream map |
| `0x0004` | `DATA` | concatenated compressed stream payloads |
| `0x0005` | `INTEGRITY` | per-stream CRC32 records |
| `0x0006` | `ENCRYPTION` | reserved; not implemented |
| `0x0007` | `RECOVERY` | reserved; not implemented |
| `0x0008` | `SEEK_INDEX` | indexed section directory / TOC |
| `0x0009` | `EXTENDED_METADATA` | reserved extension |
| `0x000A` | `USER_METADATA` | reserved extension |
| FourCC `FTR1` | `FooterIntegrity` | archive completion/global body integrity |

`FTR1` is encoded as `make_fourcc('F','T','R','1')` rather than a small numeric ID. It is a backward-ignorable extension and must be the final section when present.

Published section IDs must never be reassigned to a different meaning.

## Feature flag registry

| Bit | Name | Status |
|---:|---|---|
| 0 | `Directory` | implemented |
| 1 | `MultiStream` | implemented |
| 2 | `Integrity` | implemented |
| 3 | `SeekIndex` | implemented |
| 4 | `Encryption` | reserved / not implemented |
| 5 | `Recovery` | reserved / not implemented |
| 6 | `ExtendedMetadata` | reserved extension |
| 7 | `Kephir2` | implemented |
| 8 | `LegacyPayload` | reserved compatibility marker |
| 9 | `FooterIntegrity` | implemented |

Published bit meanings are append-only and must never be reassigned.

## Codec descriptor payload

The descriptor stores a fixed prefix followed by codec-private bytes:

| Size | Field |
|---:|---|
| 4 | codec id FourCC |
| 2 | codec major |
| 2 | codec minor |
| 2 | minimum decoder major |
| 2 | minimum decoder minor |
| 8 | codec flags |
| 4 | private-data length |
| N | private data |

Current KEPHIR FourCC is `KPHR`.

Current KEPHIR descriptor uses codec major 2 and carries the NativeK75 backend format version in private data. The reader rejects an unsupported codec or backend-format mismatch.

The AUR2 container does not duplicate transform, grain, probability-model or routing state when the KEPHIR payload is already self-describing.

## FILE_TABLE v2.0

Payload begins with entry-count varint. Each entry stores:

1. entry id varint;
2. entry type varint (`0` file, `1` directory);
3. UTF-8 canonical relative path length varint;
4. path bytes;
5. logical size varint;
6. stream id varint;
7. stream offset varint;
8. attributes varint;
9. ZigZag modification-time nanoseconds varint.

Rules:

- directory entries have logical size zero;
- an empty file may use `stream_id == 0` and no compressed payload;
- a non-empty file must map to a valid stream/range;
- duplicate entry IDs and duplicate canonical paths are rejected;
- file ranges belonging to a stream must reconstruct exactly the declared raw stream layout with no invalid overlap/gap relationship.

### Canonical archive paths

Paths:

- are UTF-8 and relative;
- use `/` separators;
- cannot contain `.` or `..` components;
- cannot contain empty/repeated components;
- cannot contain backslash separators;
- cannot use a Windows drive/root prefix;
- cannot contain NUL;
- are resolved through a safe target function that verifies the resulting path remains below the extraction root.

## Portable metadata bits

The current `attributes` field stores presence bits plus portable filesystem permission semantics.

Implemented:

- owner/group/other read/write/execute bits;
- setuid/setgid/sticky where representable by the host filesystem;
- explicit metadata-presence marker;
- explicit mtime-presence marker;
- modification time in Unix nanoseconds.

ACLs, NTFS ADS, native Windows attributes and symlink semantics are not part of the current frozen subset.

## BLOCK_TABLE / stream record

Each stream record stores:

- `stream_id` (`uint64`);
- relative `payload_offset` inside `DATA` (`uint64`);
- `compressed_size` (`uint64`);
- `raw_size` (`uint64`);
- codec id (`uint32`);
- codec flags (`uint64`).

The validator enforces bounded, non-overlapping compressed stream ranges and consistency with file-table references.

## DATA

`DATA` is the byte concatenation of the compressed stream payloads described by `BLOCK_TABLE`.

Current public extraction does **not** materialize the full DATA section. Indexed extraction reads only the current required stream range, verifies its integrity, decodes it and releases that blob before moving to the next stream.

Selective extraction reads only streams referenced by selected entries.

## INTEGRITY

The implemented integrity table contains records:

- `stream_id`;
- CRC32 of the compressed stream payload.

Before NativeK75 decode, public indexed full/selective extraction checks the stream CRC32. A mismatch is surfaced as `KEPHIR2_INTEGRITY_ERROR`.

CRC32 here is an integrity/corruption mechanism, not a cryptographic authenticity guarantee.

## SEEK_INDEX / TOC

Current indexed AUR2 places `SEEK_INDEX` as the **first TLV section** at `header.toc_offset`.

Seek payload characteristics:

- magic `SIX1`;
- seek-index version 1;
- fixed record size 32 bytes;
- record count;
- one record for every non-index section;
- payload CRC32 trailer.

Each fixed-width record stores:

- section type (`uint32`);
- section flags (`uint32`);
- section-header offset (`uint64`);
- section-payload offset (`uint64`);
- section-payload size (`uint64`).

The index cannot index itself. Offsets and lengths are validated against actual file size/layout.

`inspect` and `list` use this index to avoid reading `DATA`.

## FTR1 Footer Integrity

`FTR1` is an ignorable, versioned final section and is represented in `SEEK_INDEX`.

Current footer payload records at least:

- FTR1 magic/version;
- body size;
- CRC32 of the complete archive body preceding the footer payload according to the implemented footer definition;
- footer self-check information.

The writer computes the body CRC incrementally during file-backed finalization, avoiding a second full-archive read.

When the `FooterIntegrity` feature is set:

- exactly one FTR1 section must exist;
- it must be final;
- `header.footer_offset` must point to its section header;
- SEEK_INDEX must describe it consistently;
- body and footer CRC validation must pass.

Legacy/development AUR2 without FTR1 remains readable.

## Required product sections

For a normal current KEPHIR AUR2 archive, the functional set is:

1. `SEEK_INDEX` (current indexed writer);
2. `FILE_TABLE`;
3. `CODEC_DESCRIPTOR`;
4. `BLOCK_TABLE`;
5. `INTEGRITY`;
6. `DATA`;
7. `FTR1`.

Some legacy/development AUR2 archives may omit the derived/index/footer extensions and are handled by retained fallback paths when compatible.

## Transactional extraction semantics

Transactional publication is a runtime behavior, not additional on-disk framing.

Public full/selective extraction:

1. prepares a sibling staging directory;
2. optionally clones an existing destination to preserve unrelated/unselected files;
3. decodes, checks CRCs and restores metadata in staging;
4. publishes only after complete success;
5. discards staging on corruption, cancellation or failure.

Existing destination symlinks are rejected until explicit symlink archive semantics are designed.

## Progress semantics

NativeK75 may report 0→1 locally for each decoded stream. The AUR2 public layer remaps those local callbacks into a monotonic archive-level interval.

- full extraction weights streams by logical/raw output bytes;
- selective extraction weights each stream by selected logical bytes within that stream;
- `processed_bytes` and fraction never decrease;
- `total_bytes` remains stable for the public operation;
- one public `DONE` is emitted after transactional publication.

Progress behavior does not affect on-disk format.

## Corruption and structural rejection

The reader rejects, as applicable:

- bad magic;
- unsupported major version;
- invalid header size;
- non-zero reserved field;
- header CRC mismatch;
- invalid TOC/footer offsets;
- truncated section headers/payloads;
- contradictory/unknown section flags;
- unknown non-ignorable sections;
- malformed codec descriptor;
- malformed/trailing file-table data;
- unsafe paths;
- duplicate entry ids/paths;
- invalid stream IDs/ranges;
- DATA range overflow/overlap;
- stream/file coverage inconsistencies;
- missing/duplicate integrity records;
- stream CRC mismatch;
- malformed or inconsistent SEEK_INDEX;
- malformed/misplaced FTR1;
- footer/body checksum mismatch.

## Compatibility policy before external freeze

The current reader already retains compatibility for development AUR2 variants and KPF1 legacy extraction. Before external release, the following rules must be frozen explicitly:

- major-version rejection policy;
- minor-version forward compatibility;
- unknown feature-bit behavior;
- minimum decoder-version semantics;
- stable feature-bit and section-ID registry.

Once AUR2 v2.0 is externally published, existing IDs/bits and byte meanings must not be repurposed. Breaking framing changes require a new container major.

## Current implementation files

Core format and execution span:

- `src/kephir2/include/kephir2/aur2*.hpp`
- `src/kephir2/src/aur2*.cpp`
- `src/kephir2/src/kephir2_public_*.cpp`
- `src/kephir2/include/kephir2/kephir2_c.h`
- `src/kephir2/src/transactional_directory.cpp`
- `src/kephir2/tests/aur2_*_smoke.cpp`

Current qualification status and CI run references are maintained in `AUR2_IMPLEMENTATION_STATUS.md`.

## Still reserved / not implemented

- `ENCRYPTION`;
- `RECOVERY` / parity;
- cryptographic authentication/hashes beyond CRC-based corruption detection;
- ACL/ADS/symlink preservation;
- fully streaming NativeK75 backend I/O.

## External freeze gates

Before changing this document from pre-freeze to externally frozen:

1. final feature-bit/section-ID registry review;
2. major/minor/unknown-feature compatibility tests;
3. >4 GiB large/sparse-file qualification appropriate to the final backend architecture;
4. many-small-files stress qualification;
5. Windows Unicode/path matrix;
6. public ABI symbol/size/calling-convention audit;
7. synchronization with the canonical AURORA/KEPHIR integration handoff;
8. release-candidate roundtrip/corruption qualification.
