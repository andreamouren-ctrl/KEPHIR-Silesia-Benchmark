# Benchmark Method

## Core rule

A compression number is not accepted without decode verification.

## Lossless tests

For every candidate:
1. use the same raw source;
2. encode;
3. decode;
4. verify SHA-256;
5. record final bytes;
6. record ratio;
7. record encode/decode timing when meaningful;
8. record parameters and backend version.

## Audio references

Current major lossless references:
- FLAC
- ALAC
- WavPack

Lossy references such as Opus/AAC must remain separate.

## Video references

Current major lossless references:
- FFV1
- H.264 lossless
- HEVC lossless
- VP9 lossless
- AV1 lossless

Lossy comparisons require matched bitrate/quality methodology and must not be ranked directly against lossless AURORA.

## Research corpus

Current small video research corpus:
- Akiyo — low movement
- Foreman — medium movement
- Bus — high movement

This corpus is useful for controlled diagnostics but is not large enough for general superiority claims.

## Metrics

Lossless:
- bytes
- ratio to raw
- bits/sample or bits/pixel
- encode realtime factor
- decode realtime factor
- SHA validation

Future lossy video:
- bitrate
- PSNR
- SSIM
- VMAF
- latency
- memory

## Interpretation rule

Frontend size is diagnostic only.

The promoted objective is final KHEPRI archive size plus correct reconstruction.
