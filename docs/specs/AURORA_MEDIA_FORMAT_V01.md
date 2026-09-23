# AURORA Media Binary Format v0.1

## Status

Validated binary compatibility baseline.

Python and C++20 readers/writers have successfully exchanged files in both directions.

This is a research format baseline, not yet a frozen public standard.

## Endianness

All multi-byte integers are little-endian.

## Timescale

Default:
`1,000,000` ticks per second.

## File header — AUM1

Fields:
- 4 bytes magic: `AUM1`
- uint8 version
- uint8 flags
- uint16 track_count
- uint32 timescale
- uint32 reserved

Total: 16 bytes.

## Track header

Fields:
- uint8 track_id
- uint8 track_type
- uint8 codec
- uint8 flags
- uint32 p1
- uint32 p2
- uint32 p3
- uint32 p4

Total: 20 bytes.

Current track types:
- 1 = audio
- 2 = video

Current codec IDs:
- 1 = AURORA Audio
- 2 = AURORA Video

Current audio parameter interpretation:
- p1 = sample rate
- p2 = channel count
- p3 = bits/sample
- p4 = nominal packet sample count

Current video interpretation:
- p1 = width
- p2 = height
- p3 = FPS numerator
- p4 = FPS denominator

## Packet header

Fields:
- uint8 track_id
- uint8 flags
- uint16 reserved
- uint64 PTS
- uint64 duration
- uint32 payload_size
- uint32 payload_crc32
- uint32 reserved

Total: 32 bytes.

Flags:
- bit 0: KEY
- bit 1: RECOVERY

Payload immediately follows.

## Index

Index magic:
`AUI1`

Header:
- 4 bytes magic
- uint32 entry count

Each entry:
- uint8 track_id
- uint8 flags
- uint16 reserved
- uint64 PTS
- uint64 duration
- uint64 packet file offset
- uint32 payload size

Each index entry: 32 bytes.

## Footer

Magic:
`AUF1`

Fields:
- 4 bytes magic
- uint64 index offset
- uint64 index size
- uint32 index CRC32

Total: 24 bytes.

## Integrity

Packet CRC protects packet payload.

Index CRC protects the serialized index.

A decoder must reject:
- invalid magic;
- unsupported version;
- invalid index bounds;
- truncated packet;
- packet/index mismatch;
- CRC mismatch.

## Seeking

Seek uses indexed recovery/key packets at or before the requested PTS.

The current media session prefers a video recovery anchor when video is present.

## Streaming counterpart

AUS1 is the streaming framing format.

AUS1 is separate from the final-index AUM file layout.

## Compatibility rule

Changes that alter binary field order, field width or semantics require a format version decision and interoperability tests.
