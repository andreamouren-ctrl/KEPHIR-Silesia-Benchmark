# AURORA Audio Format Matrix Results

Date: 2026-09-26
GitHub Actions run: 36225455301
Status: PASS / PRODUCT CAPABILITY GATE

## Scope

End-to-end capability validation:

PCM -> AURORA audio frontend -> KHEPRI EXP-37A -> AUM container
-> demux -> AURORA decode -> byte-exact PCM.

The generated signal is deterministic and synthetic.
Compression ratios in this test are diagnostics only and are **not** competitive codec claims.

## Results

| Case | Channels | Rate | Bits | Raw bytes | Payload bytes | Diagnostic payload/raw |
|---|---:|---:|---:|---:|---:|---:|
| mono_s16_44100 | 1 | 44.1 kHz | 16 | 17,640 | 3,160 | 17.914% |
| stereo_s16_48000 | 2 | 48 kHz | 16 | 38,400 | 7,741 | 20.159% |
| surround_5_1_s16_48000 | 6 | 48 kHz | 16 | 115,200 | 22,340 | 19.392% |
| stereo_s24_96000 | 2 | 96 kHz | 24 | 115,200 | 19,249 | 16.709% |
| surround_5_1_s24_96000 | 6 | 96 kHz | 24 | 345,600 | 63,829 | 18.469% |
| stereo_s32_192000 | 2 | 192 kHz | 32 | 307,200 | 56,034 | 18.240% |
| surround_7_1_s32_96000 | 8 | 96 kHz | 32 | 614,400 | 181,114 | 29.478% |

## Correctness

All seven cases:
- bit-exact PCM reconstruction: PASS
- AUM payload roundtrip: PASS
- AUM audio track metadata: PASS
- recovery flag: PASS

CI markers:
- `AURORA_AUDIO_FORMAT_MATRIX_PASS 7`
- `AURORA_AUDIO_FORMAT_MATRIX_JSON_PASS`

## Product support checkpoint

Validated integer PCM families now include:
- mono;
- stereo;
- 5.1;
- 7.1;
- signed 16-bit;
- signed 24-bit;
- signed 32-bit;
- 44.1 / 48 / 96 / 192 kHz examples.

The public packet bridge now also validates:
- bits/sample is one of 16/24/32;
- channel count is 1..32;
- sample rate is 8 kHz..384 kHz;
- PCM payload is frame-aligned.

## Important architecture note

16-bit PCM uses the canonical promoted FULL256 + TAIL16 path.

24/32-bit PCM currently uses the generalized KMRL v2 path.
The format matrix validates correctness, not that the high-resolution path has reached the
same compression maturity as canonical s16.

## Decision

**PROMOTE the format-support capability gate.**

Next audio completeness gates:
- real high-resolution music/speech compression corpus;
- long-duration multichannel soak tests;
- channel-layout semantics in the public format/API;
- native in-process production audio backend to remove temporary-file/subprocess overhead.
