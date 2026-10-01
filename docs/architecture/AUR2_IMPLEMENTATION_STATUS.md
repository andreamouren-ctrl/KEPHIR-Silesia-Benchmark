# AUR2 Implementation Status

**Branch:** `development/aur2-container-core`  
**Target base:** `development/kephir-2-core`  
**Status:** active development

## Implemented

- AUR2 64-byte fixed header.
- Magic `AUR2\r\n\x1A\n`.
- Little-endian fixed-width fields.
- Header CRC32.
- Version fields and reserved-field validation.
- Feature flags.
- TLV section framing.
- Required/ignorable unknown-section policy.
- FILE_TABLE serialization/deserialization.
- Explicit DIRECTORY entries, including empty directories.
- UTF-8 canonical relative archive paths.
- Path traversal and absolute-path rejection.
- Duplicate entry id/path rejection.
- CODEC_DESCRIPTOR with KEPHIR FourCC `KPHR`.
- KEPHIR backend format-version binding.
- BLOCK_TABLE / stream records.
- Contiguous non-overlapping DATA stream validation.
- Exact decoded stream coverage validation by file ranges.
- Single-file AUR2 writer/reader bound to `CompressionBackend`.
- Empty-file representation without unnecessary compressed stream.
- Directory AUR2 writer/reader.
- SMART directory packing reuse.
- FLAT directory packing reuse.
- NativeK75 payload roundtrip tests.
- File, directory, empty-file and empty-directory test coverage.
- Linux/Windows AUR2 CI workflow definition.

## Current AUR2 required sections

1. `FILE_TABLE`
2. `CODEC_DESCRIPTOR`
3. `BLOCK_TABLE`
4. `DATA`

Optional extension section ids are reserved for integrity, encryption, recovery, seek index and metadata.

## Not yet implemented

- INTEGRITY section beyond fixed-header CRC32.
- File/stream cryptographic hashes.
- SEEK_INDEX.
- ENCRYPTION.
- RECOVERY.
- Extended metadata preservation.
- mtime capture/restore (field exists, execution path still writes zero).
- Windows file attributes capture/restore (field exists, execution path still writes zero).
- public C ABI inspect/list/test/selective extraction functions.
- on-disk streaming writer; current AUR2 encoder returns an in-memory `ByteBuffer`.
- on-disk range reader; current decoder parses an in-memory archive buffer.
- large-archive bounded-memory qualification.
- AUR1 compatibility adapter.

## Release gates

AUR2 must not be declared externally frozen until:

- Linux build/test PASS;
- Windows build/test PASS;
- core regression CTest PASS;
- corruption matrix PASS;
- path-safety matrix PASS;
- large file >4 GiB PASS;
- many-small-files PASS;
- cancellation/progress integration PASS;
- public C API integration PASS;
- final format review and byte-level freeze complete.

## Next implementation step

Implement the `INTEGRITY` section and archive inspection model, then expose read-only AUR2 metadata through the stable C ABI before adding encryption/recovery.
