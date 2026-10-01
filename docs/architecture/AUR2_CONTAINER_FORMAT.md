# AUR Container v2.0 — Binary Core Specification

**Status:** implementation draft / development branch  
**Branch:** `development/aur2-container-core`  
**Scope:** stable product container framing above the KEPHIR codec payload.

## Design boundary

`.aur` is the AURORA product container. KEPHIR is the compression codec/backend carried by that container. AUR2 must not expose research experiment identifiers or require the decoder to reproduce encoder-side routing decisions.

## Byte order

All fixed-width integers are little-endian. Variable-width integers used by the file table use the existing KEPHIR unsigned varint encoding. Signed modification time is encoded with ZigZag + unsigned varint.

## Fixed header

The v2.0 fixed header is exactly 64 bytes.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | magic `AUR2\r\n\x1A\n` |
| 8 | 2 | container major |
| 10 | 2 | container minor |
| 12 | 4 | header size |
| 16 | 8 | feature flags |
| 24 | 8 | archive id |
| 32 | 8 | logical size |
| 40 | 8 | TOC offset |
| 48 | 8 | footer offset |
| 56 | 4 | header CRC32 |
| 60 | 4 | reserved, must be zero |

For v2.0 the CRC32 covers bytes `[0, 56)`. The CRC field itself and the reserved field are not included.

Current v2.0 rules:

- major must be `2`;
- header size must be `64`;
- reserved must be zero;
- footer offset is currently zero;
- if sections exist, TOC offset is `64`;
- if no sections exist, TOC offset is zero.

## TLV sections

Every section uses a 16-byte header:

| Size | Field |
|---:|---|
| 4 | type |
| 4 | flags |
| 8 | payload length |

Initial section types:

- `0x0001` FILE_TABLE
- `0x0002` CODEC_DESCRIPTOR
- `0x0003` BLOCK_TABLE
- `0x0004` DATA
- `0x0005` INTEGRITY
- `0x0006` ENCRYPTION
- `0x0007` RECOVERY
- `0x0008` SEEK_INDEX
- `0x0009` EXTENDED_METADATA
- `0x000A` USER_METADATA

Section flags:

- bit 0: IGNORABLE
- bit 1: REQUIRED

A section cannot be both REQUIRED and IGNORABLE. An unknown section is accepted only when IGNORABLE is set. Unknown non-ignorable sections are rejected.

## Feature flags

Initial bits:

- bit 0 DIRECTORY
- bit 1 MULTISTREAM
- bit 2 INTEGRITY
- bit 3 SEEK_INDEX
- bit 4 ENCRYPTION
- bit 5 RECOVERY
- bit 6 EXTENDED_METADATA
- bit 7 KEPHIR2
- bit 8 LEGACY_PAYLOAD

Published bit meanings must never be reassigned.

## Codec descriptor payload

Fixed prefix followed by codec-private bytes:

| Size | Field |
|---:|---|
| 4 | codec id FourCC |
| 2 | codec major |
| 2 | codec minor |
| 2 | minimum decoder major |
| 2 | minimum decoder minor |
| 8 | codec flags |
| 4 | private data length |
| N | private data |

KEPHIR FourCC is `KPHR`.

The outer AUR2 container must not duplicate transform, grain, probability-model or other backend details when the KEPHIR payload is already self-describing.

## File table v2.0 payload

The file table starts with entry count varint. Every entry stores:

1. entry id varint;
2. entry type varint (`0` file, `1` directory);
3. UTF-8 canonical relative path length varint;
4. path bytes;
5. logical size varint;
6. stream id varint;
7. stream offset varint;
8. attributes varint;
9. ZigZag modification-time nanoseconds varint.

Directory entries must have logical size zero. This allows explicit preservation of empty directories.

Canonical archive paths:

- use `/` separator;
- must be relative;
- cannot contain `.` or `..` components;
- cannot contain repeated empty components;
- cannot contain `\\` separators;
- cannot use a Windows drive prefix;
- cannot contain NUL.

Duplicate entry ids and duplicate paths are rejected.

## Integrity and corruption handling

The decoder rejects:

- bad magic;
- unsupported major version;
- invalid header size;
- non-zero reserved field;
- header CRC mismatch;
- invalid TOC/footer offsets for v2.0;
- truncated section headers/payloads;
- contradictory or unknown section flags;
- unknown required/non-ignorable sections;
- malformed codec descriptor;
- malformed/trailing file-table data;
- unsafe archive paths;
- duplicate file ids/paths.

## Current implementation files

- `src/kephir2/include/kephir2/aur2.hpp`
- `src/kephir2/src/aur2.cpp`
- `src/kephir2/tests/aur2_smoke.cpp`

## Next implementation stages

1. stream/block descriptor and actual KEPHIR payload binding;
2. end-to-end file archive writer/reader;
3. end-to-end directory archive writer/reader;
4. integrity section;
5. public C API `inspect`, `list`, `test`, selected extraction;
6. seek index;
7. encryption/recovery extensions only after their separate security/design freeze.

No AUR2 v2.0 field is considered frozen for external release until Release Candidate qualification is complete.
