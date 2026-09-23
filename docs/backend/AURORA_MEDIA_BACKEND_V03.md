# AURORA Media Backend v0.3 — Hardened Core Interfaces

Date: 2026-09-23
Branch: research/khepri-stream-codec
Validation run: 35843071898
Result: PASS

## Milestone summary

Backend v0.3 hardens the C++20 core without changing the AUM v0.1 binary format.

## Added

### Typed codec interfaces
- IKhepriBackend
- IAudioEncoder
- IAudioDecoder
- IVideoEncoder
- IVideoDecoder
- AudioFormat / VideoFormat
- AudioEncodeConfig / VideoEncodeConfig
- EncodedPacket

### Typed backend error model
AuroraMediaError + ErrorCode now distinguish:
- invalid arguments
- unsupported versions/codecs
- corrupt headers/index/packets
- CRC mismatches
- truncated input
- resource limits
- sequence gaps
- encode/decode failures
- I/O failures
- internal invariant failures

Container and stream backends now use typed AURORA errors for their principal failure paths.

### Resource limits
Configurable Limits now bound:
- maximum track count
- maximum packet bytes
- maximum index entries
- maximum index bytes
- maximum incremental stream buffer bytes

These limits are enforced during muxing, demuxing and stream parsing.

### Corruption matrix
Validated rejection cases:
1. bad file magic
2. unsupported version
3. truncated header
4. truncated footer
5. bad footer magic
6. bad index CRC
7. bad packet CRC
8. packet/index size mismatch

Valid control file continues to decode.

### In-process KHEPRI contract
FunctionKhepriBackend implements IKhepriBackend using pure memory buffers.

This is the architectural seam for the future native KHEPRI library API:
- ByteView -> Bytes encode
- ByteView -> Bytes decode

The current EXP-37A implementation is still CLI/file-oriented, so this milestone does not falsely claim that the engine itself has already been converted to an in-process library. It establishes and validates the interface that the refactored KHEPRI core must satisfy.

## CI gates passing

The following all pass together with -Wall -Wextra -Werror:
- container/stream backend build
- media session backend build
- typed codec interfaces
- resource limits
- AUM corruption matrix
- in-process KHEPRI contract
- Python -> C++ binary interoperability
- C++ -> Python binary interoperability
- C++ media session

## Compatibility

AUM v0.1 binary layout remains unchanged.

## Next milestone

B04 continues with extraction of the actual EXP-37A compression/decompression logic from the CLI-oriented generated source into reusable memory-buffer functions, connected through IKhepriBackend.

No GUI work is part of this milestone.
