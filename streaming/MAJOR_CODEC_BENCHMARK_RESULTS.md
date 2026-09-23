# AURORA / KHEPRI — Major Audio & Video Codec Benchmark

Date: 2026-09-23  
GitHub Actions run: 35833190903  
Backend: **KHEPRI EXP-37A PREDICTIVE-DUAL-MATCH**

All lossless candidates were decoded and verified bit-exact by SHA.

## Audio lossless

Source: Xiph Sintel trailer audio -> stereo PCM s16le 48 kHz, 52 s, 9,984,000 bytes.

| Codec | Bytes | % PCM | Encode realtime | Decode realtime |
|---|---:|---:|---:|---:|
| WavPack (high compression setting) | **4,587,265** | **45.946%** | 0.36x | 248.3x |
| FLAC level 8 | 4,663,310 | 46.708% | 127.5x | 540.8x |
| ALAC | 4,862,860 | 48.707% | 136.9x | 328.3x |
| **AURORA/KHEPRI KMRL+TAIL16+EXP37A** | **5,542,173** | **55.511%** | **6.46x** | **15.52x** |

AURORA/KHEPRI is currently:
- 18.85% larger than FLAC;
- 13.97% larger than ALAC;
- 20.82% larger than this WavPack high-compression result.

The Python media frontend dominates AURORA/KHEPRI timing and is not representative of an optimized C++ implementation.

Streaming lossy references, not directly comparable to AURORA lossless:
- Opus 128 kb/s: 861,919 bytes
- AAC 128 kb/s: 859,057 bytes

## Video lossless

Common source format: raw YUV420p 8-bit, 176x144.

AURORA has two current research controls:
- TEMP: previous-frame temporal residual
- MC8R4: bounded 8x8 integer-pixel motion compensation, radius 4

Both feed KHEPRI EXP-37A.

### Akiyo — low motion, 300 frames

| Codec | Bytes | % raw | bpp | Encode realtime |
|---|---:|---:|---:|---:|
| HEVC lossless | **1,548,805** | **13.580%** | **1.630** | 5.34x |
| H.264 lossless | 1,550,700 | 13.597% | 1.632 | 35.90x |
| AV1 lossless | 1,664,745 | 14.597% | 1.752 | 2.42x |
| VP9 lossless | 1,697,847 | 14.887% | 1.786 | 3.11x |
| **AURORA TEMP + EXP37A** | **2,208,653** | **19.366%** | **2.324** | **6.54x** |
| AURORA MC8R4 + EXP37A | 2,209,687 | 19.375% | 2.325 | 0.82x |
| FFV1 | 3,468,622 | 30.414% | 3.650 | 45.49x |

AURORA TEMP is 36.32% smaller than FFV1 on Akiyo, but remains about 42.6% larger than HEVC lossless.

### Foreman — medium motion, 300 frames

| Codec | Bytes | % raw | bpp |
|---|---:|---:|---:|
| HEVC lossless | **3,722,889** | **32.643%** | **3.917** |
| AV1 lossless | 3,790,903 | 33.240% | 3.989 |
| VP9 lossless | 3,809,998 | 33.407% | 4.009 |
| H.264 lossless | 3,893,089 | 34.136% | 4.096 |
| FFV1 | 5,295,415 | 46.431% | 5.572 |
| **AURORA MC8R4 + EXP37A** | **5,779,455** | **50.676%** | **6.081** |
| AURORA TEMP + EXP37A | 6,076,824 | 53.283% | 6.394 |

Best current AURORA is 9.14% larger than FFV1 and 55.24% larger than HEVC lossless.

### Bus — high motion, 75 frames

| Codec | Bytes | % raw | bpp |
|---|---:|---:|---:|
| HEVC lossless | **1,269,735** | **44.533%** | **5.344** |
| VP9 lossless | 1,272,775 | 44.640% | 5.357 |
| H.264 lossless | 1,311,224 | 45.988% | 5.519 |
| AV1 lossless | 1,336,862 | 46.888% | 5.627 |
| FFV1 | 1,593,314 | 55.882% | 6.706 |
| **AURORA MC8R4 + EXP37A** | **1,841,866** | **64.600%** | **7.752** |
| AURORA TEMP + EXP37A | 2,008,806 | 70.455% | 8.455 |

Best current AURORA is 15.60% larger than FFV1 and 45.06% larger than HEVC lossless.

## Aggregate research view

If the smaller AURORA mode is selected per clip:
- AURORA: 9,829,974 bytes
- FFV1: 10,357,351 bytes
- H.264 lossless: 6,755,013 bytes
- HEVC lossless: 6,541,429 bytes
- VP9 lossless: 6,780,620 bytes
- AV1 lossless: 6,792,510 bytes

This gives AURORA about 5.09% fewer bytes than FFV1 across these three small test clips, but about 50.27% more bytes than HEVC lossless.

This aggregate is a research indicator only: AURORA currently chooses different research transforms by content and does not yet implement a finalized per-GOP mode router.

## Streaming lossy video reference at nominal 300 kb/s

Lossy data is not ranked against AURORA because the current AURORA video path is lossless.

Akiyo:
- H.264: 387,830 B, PSNR 44.770 dB
- HEVC: 317,859 B, PSNR 44.827 dB
- VP9: 362,424 B, PSNR 45.097 dB
- AV1: 376,810 B, PSNR 45.266 dB

Foreman:
- H.264: 400,026 B, PSNR 29.570 dB
- HEVC: 386,756 B, PSNR 29.639 dB
- VP9: 406,312 B, PSNR 29.608 dB
- AV1: 388,892 B, PSNR 29.666 dB

Bus:
- H.264: 187,504 B, PSNR 24.256 dB
- HEVC: 172,906 B, PSNR 24.273 dB
- VP9: 188,618 B, PSNR 24.218 dB
- AV1: 184,660 B, PSNR 24.271 dB

## Engineering decision

Current position:
1. Audio: architecture works, but compression ratio must improve materially before challenging mature lossless audio codecs.
2. Video low-motion: KHEPRI temporal residuals are strong and already beat FFV1 on Akiyo.
3. Video medium/high-motion: motion representation is the main weakness.
4. The next high-value work is not another entropy-backend micro-tune. It is a stronger reversible motion/residual representation and adaptive per-GOP routing.
5. Lossy/perceptual AURORA modes must remain a separate future track and must not be compared directly with the current lossless path.
