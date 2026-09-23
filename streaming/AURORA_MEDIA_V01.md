# AURORA Media v0.1 — First End-to-End Working Baseline

Date: 2026-09-23  
Validation workflow: **AURORA Media v0.1 End-to-End**  
GitHub Actions run: **35837750505**  
Result: **PASS**

## Goal reached

AURORA Media now has a first native, testable end-to-end stack that does not
depend on FFmpeg, libavformat, libavcodec or third-party muxer/demuxer code in
the AURORA playback/encoding core.

The v0.1 accepts canonical raw media inputs:
- audio: PCM s16le;
- video: YUV420p 8-bit.

External import adapters for MP4/MKV/MOV/etc. remain outside the core.

## Components implemented

### Codec bridge
File: `streaming/aurora_media_codec_v01.py`

Audio packet path:
PCM -> KMRL FULL256 + TAIL16 -> KHEPRI EXP-37A -> independent payload

Video packet path:
YUV420p -> KSV-05 TEMP/MC8R4 routing -> KHEPRI EXP-37A -> independent payload

### Native AURORA container
File: `streaming/aurora_media_container_v01.py`

Implements:
- magic/version header;
- track table;
- audio/video track metadata;
- packet timestamps;
- packet durations;
- recovery/key flags;
- CRC32 per packet;
- deterministic final index;
- footer locating the index;
- index CRC;
- random packet access;
- recovery-point seek.

Working extension in research: `.aum`.

### Native muxer / demuxer
Implemented in the container module.

No FFmpeg/libavformat is used to create or read `.aum`.

### A/V pipeline
File: `streaming/aurora_media_av_v01.py`

Implements:
- audio packetization;
- video packetization;
- timestamp generation;
- A/V packet interleaving;
- muxing;
- demuxing;
- complete audio/video decode.

### AURORA Converter v0.1
File: `streaming/aurora_converter_v01.py`

Current native input boundary:
- raw PCM s16le;
- raw YUV420p8.

Future arbitrary-format import can use optional external adapters before this
boundary, without becoming part of the AURORA codec/container.

### AURORA Player Core v0.1
File: `streaming/aurora_player_core_v01.py`

Implements:
- native demux;
- native AURORA audio/video decode;
- PTS ordered A/V timeline;
- recovery-point seek;
- callback sinks for decoded audio/video;
- headless verification.

The graphical renderer and physical audio output are deliberately above this
core and are not required for format correctness.

### AURORA Stream Protocol v0.1
File: `streaming/aurora_stream_protocol_v01.py`

Implements:
- packet magic/version;
- sequence number;
- track id;
- flags;
- PTS;
- duration;
- payload length;
- CRC32;
- ordered receiver with sequence-gap detection.

It defines framing over an ordered byte transport; it is not tied to TCP, UDP
or a third-party streaming protocol.

## End-to-end validation result

Synthetic sources were generated directly in Python. FFmpeg was not used.

Result:
- status: PASS
- AURORA container: 17,716 bytes
- tracks: 2
- packets: 7
  - audio packets: 5
  - video packets: 2
- decoded audio: 192,000 bytes
- decoded video: 1,520,640 bytes

Audio SHA-256:
- source: `bd7bfce6da2105c980706adba20fc19ef746579587255237d2ff19f11b449d02`
- decoded: `bd7bfce6da2105c980706adba20fc19ef746579587255237d2ff19f11b449d02`

Video SHA-256:
- source: `ccd417b50327127c6d0569a6676d265fd4fb7d5660100a5f808a50caa3a7380a`
- decoded: `ccd417b50327127c6d0569a6676d265fd4fb7d5660100a5f808a50caa3a7380a`

Integrity:
- corrupted container payload rejected by packet CRC: PASS
- corrupted stream packet rejected by stream CRC: PASS
- native mux/demux: PASS
- external multimedia dependency in core: FALSE

## Proprietary-code boundary

AURORA now owns the implementation of:
- container;
- muxing;
- demuxing;
- packet framing;
- indexing;
- seek;
- timestamp/interleave logic;
- stream framing;
- player orchestration;
- codec integration.

Concepts such as CRC, timestamps, muxing, packetization, seeking, temporal
prediction and motion compensation are established engineering concepts and are
not claimed as inventions merely because this implementation is ours.

Candidate proprietary/IP research remains focused on genuinely KHEPRI-specific
mechanisms such as residual geometry, backend coupling and future adaptive state
behavior, subject to prior-art review.

## v0.1 limitations

This is a functional research baseline, not a production release.

Not yet included:
- native window/display renderer;
- native audio device backend;
- subtitles;
- chapters/attachments;
- metadata tags;
- encryption;
- network socket implementation;
- arbitrary MP4/MKV/MOV input without an import adapter;
- C++20 production rewrite;
- finalized public file extension/specification.

## Next production milestone

Port the validated binary specification and packet model to C++20 while keeping
the Python implementation as the executable reference model.
