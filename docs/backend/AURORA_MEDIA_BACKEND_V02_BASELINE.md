# AURORA Media Backend v0.2 — C++20 Core Baseline

Date: 2026-09-23  
Branch: `research/khepri-stream-codec`

Validation:
- Python reference end-to-end: run 35837750505 — PASS
- C++20 interop + session backend: run 35839731226 — PASS

## Scope

Backend only. No GUI, renderer or audio-device integration.

## C++20 modules

- `streaming/cpp/AuroraMediaContainer.h/.cpp`
  - native AUM v0.1 reader/writer
  - little-endian deterministic serialization
  - track table
  - packets
  - CRC32
  - final index/footer
  - packet bounds validation
  - recovery-point seek

- `streaming/cpp/AuroraStreamProtocol.h/.cpp`
  - AUS1 packet framing
  - sequence number
  - track/flags
  - PTS/duration
  - CRC32
  - ordered receiver
  - incremental byte-stream parser

- `streaming/cpp/AuroraMediaSession.h/.cpp`
  - media-track validation
  - deterministic PTS timeline
  - sequential packet access
  - audio/video track discovery
  - recovery-point seek anchor
  - reset/cursor state

## Binary compatibility

The format now has two independently implemented readers/writers:

1. Python executable reference model.
2. C++20 backend implementation.

Validated:
- Python writes -> C++ reads: PASS
- C++ writes -> Python reads: PASS
- native C++ write/read: PASS
- stream incremental parsing: PASS
- stream CRC rejection: PASS
- media-session seek/timeline: PASS

This freezes the current AUM v0.1 binary layout as the backend compatibility
baseline while development continues.

## Build quality gate

C++20 tests compile with:

`-O2 -std=c++20 -Wall -Wextra -Werror`

## Current dependency boundary

The C++ container/session/stream backend has no FFmpeg/libavcodec/libavformat
dependency.

KHEPRI codec payload production remains connected through the current research
implementation. The next backend milestone is to port the audio/video codec
bridge into native C++20 while preserving byte compatibility with the Python
reference implementation.

## Next backend sequence

1. C++20 codec interface and typed error model.
2. Native KHEPRI process/in-process adapter.
3. Audio packet codec C++20.
4. Video packet codec C++20.
5. Incremental mux/demux APIs for non-seekable streams.
6. fuzz/corruption/limits tests.
7. multithreaded encode/decode scheduler.
