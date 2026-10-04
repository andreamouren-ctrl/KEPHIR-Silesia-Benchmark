# AUR2 Implementation Status

**Branch:** `development/aur2-container-core`  
**Target base:** `development/kephir-2-core`  
**PR:** #110  
**Snapshot:** 2026-10-04  
**Status:** implementation/qualification candidate; **format not externally frozen yet**

## Executive status

AUR2 is now a functioning product container around the KEPHIR native backend rather than a format draft. The public KEPHIR C ABI writes AUR2, reads current AUR2 through indexed file-backed paths, and preserves KPF1 legacy extraction fallback.

The current implementation has passed Linux and Windows CI for framing, K75 roundtrip, SMART/FLAT directories, integrity, indexed inspection, metadata, public C ABI, selective extraction, file-backed I/O, transactional publication, cancellation/corruption rollback and multi-stream progress.

The remaining work before an external byte-level format freeze is mainly long-horizon compatibility qualification and optional features, not basic container functionality.

## Implemented container format

- Fixed 64-byte AUR2 header.
- Magic `AUR2\r\n\x1A\n`.
- Little-endian fixed-width serialization.
- Header CRC32.
- Major/minor container version fields.
- Reserved-field validation.
- 64-bit feature flags.
- Active `toc_offset` and `footer_offset` validation.
- TLV section framing.
- Required/ignorable unknown-section policy.
- `FILE_TABLE` serialization/deserialization.
- Explicit `FILE` and `DIRECTORY` entries, including empty directories.
- Empty-file representation without an unnecessary compressed stream.
- UTF-8 canonical relative archive paths.
- Absolute/rooted/path-traversal rejection.
- Duplicate entry id/path rejection.
- `CODEC_DESCRIPTOR` with KEPHIR FourCC `KPHR`.
- Codec major/minor and NativeK75 backend-format binding.
- `BLOCK_TABLE` / stream records.
- `DATA` payload section.
- Contiguous, non-overlapping compressed-stream range validation.
- Exact decoded stream coverage validation by file ranges.
- `INTEGRITY` table with per-stream CRC32.
- `SEEK_INDEX`/TOC as the first section, with fixed-width records and its own CRC32.
- `FTR1` footer-integrity section with body-size marker, global body CRC32 and footer self-check.
- Footer represented in the Seek Index without circular checksum dependency.

## Filesystem metadata

Implemented and tested:

- modification time stored as Unix nanoseconds;
- portable owner/group/other rwx permission bits;
- metadata capture during public compression;
- metadata restore after full extraction;
- metadata restore after selective extraction;
- directory timestamps restored deepest-first after children are created;
- metadata lookup through indexed `FILE_TABLE` without loading `DATA`.

Current deliberate exclusions:

- Windows ACLs;
- NTFS Alternate Data Streams;
- native Windows attribute set beyond portable rwx semantics;
- symlink preservation.

Existing destination symlinks are rejected by transactional extraction until canonical symlink semantics are designed, preventing staging-copy/path traversal surprises.

## Directory packing and payloads

- Single-file AUR2 writer/reader bound to `CompressionBackend`.
- Directory writer/reader.
- SMART directory packing reuse.
- FLAT directory packing reuse.
- NativeK75 payload roundtrip.
- File, directory, empty-file and empty-directory coverage.
- Exact stream-to-file mapping with gap/overlap rejection.

The AUR2 layer does not expose K75 internals such as transform or grain decisions to the GUI contract. Decoder-required backend parameters remain self-contained in the codec payload/descriptor.

## File-backed I/O

### Read path

Current indexed AUR2 extraction is file-backed:

1. read/validate header + `SEEK_INDEX` + metadata sections;
2. locate the required compressed stream in `DATA`;
3. read only that stream blob;
4. verify the stream CRC32;
5. decode through NativeK75;
6. release the blob before advancing to the next stream.

Selective extraction reads only streams referenced by selected entries.

`inspect` and `list` do not load `DATA`. Deep `test_archive` performs payload/integrity/decompression verification.

### Write/finalization path

The public writer first obtains the base AUR2 payload from the codec execution path, then performs one file-backed finalization pass that:

- captures filesystem metadata into `FILE_TABLE`;
- rebuilds `SEEK_INDEX`;
- appends `FTR1`;
- copies unchanged section payloads including `DATA` in bounded chunks;
- computes the footer body CRC incrementally;
- publishes the completed archive atomically.

The historical metadata → seek → footer whole-archive rewrite chain remains compiled only for compatibility/internal history and is no longer the public `kephir2_compress()` path.

**Important limitation:** NativeK75 still produces/consumes one contiguous compressed blob per stream. AUR2 is therefore bounded by the largest active stream, not yet fully streaming at codec level.

## Transactional extraction

Public full and selective extraction use sibling staging directories.

Semantics:

1. prepare staging tree;
2. optionally clone an existing destination when overwrite/selective semantics require preservation;
3. decode and verify into staging;
4. restore metadata;
5. publish only after successful completion;
6. discard staging on corruption, cancellation or failure.

Validated properties:

- corrupted `DATA` returns `KEPHIR2_INTEGRITY_ERROR` without modifying the original destination;
- cancellation returns `KEPHIR2_CANCELLED` without publishing partial output;
- unrelated existing files survive overwrite/selective extraction;
- selected files are replaced while unselected colliding files remain unchanged;
- final `DONE` is emitted only after transactional publication.

## Progress model

NativeK75 reports 0→100% locally for each stream. AUR2 now wraps those reports in an archive-level progress adapter.

For full extraction:

- stream weight = stream logical/raw output bytes.

For selective extraction:

- stream weight = logical bytes of the selected files within that stream.

Public guarantees tested across multiple SMART streams:

- fraction never decreases;
- processed bytes never decrease;
- total bytes stay stable;
- selective totals represent selected logical bytes rather than the full decoded group;
- exactly one public `DONE` event is emitted after commit.

## Public C ABI implemented

Current public surface includes:

```text
kephir2_api_version
kephir2_engine_version
kephir2_create
kephir2_destroy
kephir2_options_init_v1
kephir2_get_capabilities
kephir2_compress
kephir2_extract
kephir2_inspect
kephir2_list_entries
kephir2_test_archive
kephir2_extract_selected
kephir2_status_name
```

The ABI uses opaque engine handles, versioned `struct_size` records, UTF-8 paths, progress callbacks and cooperative cancellation callbacks.

Public profiles remain:

```text
AUTO
FAST
BALANCED
MAX
```

## Compatibility

Implemented:

- public writer: AUR2;
- public reader: AUR2;
- KPF1 legacy file extraction fallback;
- KPF1 legacy directory extraction fallback;
- legacy/non-indexed AUR2 fallback paths retained where required.

Not yet claimed:

- a general AUR1 compatibility adapter beyond the KPF1 legacy paths actually tested.

## Qualification record

| Area | Result | CI run |
|---|---|---:|
| Footer Integrity + `footer_offset` + Capability Query | Linux + Windows PASS | `36850557823` |
| Indexed ranged reader | Linux + Windows PASS | `36851322831` |
| Public bounded-memory full/selective extraction | Linux + Windows PASS | `36916395830` |
| File-backed finalizer module | Linux + Windows PASS | `36917547860` |
| Public writer using file-backed finalizer | Linux + Windows PASS | `36918208737` |
| Transactional staging helper | Linux + Windows PASS | `36918771943` |
| Public corruption/cancellation rollback | Linux + Windows PASS | `37237322025` |
| Monotonic multi-stream full/selective progress | Linux + Windows PASS | `37237913015` |
| Historical EXP-111 full build/test/Silesia validation after packing fix | PASS | `36916395796` |
| AUR2 scale qualification | PASS | `37238274255` |

## Scale qualification baseline

Public C ABI; Ubuntu 24.04 GitHub runner; deterministic mixed directory; encode/decode run in separate processes; SHA-256 roundtrip verified.

| Fixture | Archive ratio | Encode | Decode | Encode peak RSS | Decode peak RSS |
|---:|---:|---:|---:|---:|---:|
| 16 MiB | 25.0275% | 29.893 MiB/s | 280.917 MiB/s | 84.95 MiB | 31.69 MiB |
| 64 MiB | 25.0238% | 32.668 MiB/s | 277.182 MiB/s | 106.15 MiB | 43.66 MiB |

Interpretation:

- this is an AUR2 I/O/container qualification fixture, **not** a Silesia or competitor ratio claim;
- public throughput on this fixture exceeds the historical project targets of 20–30 MB/s encode and 150–200 MB/s decode;
- logical input grows 4× from 16→64 MiB while decode peak RSS grows from 31.69→43.66 MiB, consistent with one-stream-at-a-time file-backed extraction;
- encode peak still includes the current contiguous backend payload behavior and therefore remains a future optimization target.

Artifact:

```text
run:      37238274255
artifact: 11316497525
SHA256:   06fa6352c0fba644d200f5e44b87b18c19c2a36698c602157631dafa9440493a
```

## CI policy

- `AUR2 Container Smoke` remains the normal Linux/Windows gate for AUR2 code.
- `AUR2 Scale Qualification` is manual (`workflow_dispatch`) after establishing the baseline, to avoid expensive large-fixture runs on every commit.
- EXP-111/Silesia is guarded to the dedicated research head branch (or explicit manual dispatch), so AUR2 PR synchronization does not consume a Silesia benchmark runner.

## Not yet implemented / advertised

- encryption;
- recovery/parity;
- cryptographic file/stream hashes beyond the current CRC integrity model;
- ACL / ADS / symlink preservation;
- fully streaming NativeK75 encode/decode;
- externally frozen AUR2 byte-level specification.

## Remaining release/freeze gates

Before declaring AUR2 externally frozen:

- final byte-level format review;
- confirm major/minor compatibility policy against the actual reader behavior;
- >4 GiB real/sparse-file qualification appropriate to the final large-file architecture;
- many-small-files stress qualification;
- final Windows path/Unicode matrix;
- final public ABI symbol/`sizeof`/calling-convention audit;
- update the canonical AURORA/KEPHIR integration handoff document;
- freeze container feature-bit and section-id registry.

## Next engineering step

AUR2 core I/O and public integration are now mature enough to stop adding unrelated container features before the format review. The next product work should be:

1. final AUR2 format/ABI freeze review;
2. documentation synchronization into the canonical integration handoff;
3. merge into `development/kephir-2-core` after final Linux/Windows gate;
4. return to KEPHIR compression-core R&D, where the main open product target remains Silesia ratio <28% and later throughput optimization under the real corpus.
