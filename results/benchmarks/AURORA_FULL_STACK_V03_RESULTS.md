# AURORA Media v0.3 — Full-Stack Codec Benchmark

Date: 2026-09-23
GitHub Actions run: 35843970101
Audio packet-horizon run: 35844650459

## Scope

This benchmark measures final files, not only codec payloads.

AURORA includes:
- AUM v0.1 container;
- track metadata;
- packet headers;
- CRC;
- final index;
- recovery-point packetization;
- KMRL FULL256 + TAIL16 audio frontend;
- KSV-05 20-frame adaptive video routing;
- KHEPRI EXP-37A backend.

Reference codecs include their produced FLAC/M4A/WV/MKV file overhead.

All lossless outputs were decoded and SHA-verified.

## Audio — complete AUM file

Source:
- PCM s16le
- stereo 48 kHz
- 52 s
- 9,984,000 raw bytes

Initial streaming structure used 200 ms independent audio packets.

| Codec | Final bytes | % raw |
|---|---:|---:|
| WavPack high compression | **4,587,265** | **45.946%** |
| FLAC level 8 | 4,663,310 | 46.708% |
| ALAC | 4,862,860 | 48.707% |
| AURORA AUM, 200 ms recovery packets | 5,825,143 | 58.345% |

At 200 ms, AURORA is:
- 24.91% larger than FLAC;
- 19.79% larger than ALAC;
- 26.99% larger than WavPack high compression.

The difference versus the earlier single-stream AURORA result is not mainly AUM metadata. It is the repeated KHEPRI state reset caused by 260 independently decodable packets.

## Audio packet-horizon diagnostic

| Recovery horizon | Packets | Final AUM bytes | % raw | Estimated pure AUM metadata |
|---|---:|---:|---:|---:|
| 200 ms | 260 | 5,825,143 | 58.345% | 16,708 B |
| 500 ms | 104 | 5,715,709 | 57.249% | 6,724 B |
| 1000 ms | 52 | 5,599,490 | 56.085% | 3,396 B |
| **2000 ms** | **26** | **5,546,958** | **55.558%** | **1,732 B** |

The previous non-container single-stream AURORA result was approximately 5,542,173 bytes.

Therefore the 2-second full AUM structure is only 4,785 bytes above the earlier single-stream payload result, while still preserving bounded recovery packets.

This shows that the structural container overhead itself is very small. The significant penalty at short horizons comes from compression-state resets.

For future streaming work, recovery horizon should therefore be treated as a codec state variable, not merely a container setting.

## Video — complete AUM file

### Akiyo, low motion

| Codec | Final bytes | % raw |
|---|---:|---:|
| HEVC lossless | **1,548,805** | **13.580%** |
| H.264 lossless | 1,550,700 | 13.597% |
| AV1 lossless | 1,664,745 | 14.597% |
| VP9 lossless | 1,697,847 | 14.887% |
| **AURORA full AUM** | **2,176,720** | **19.086%** |
| FFV1 | 3,468,622 | 30.414% |

AURORA full-stack is:
- 37.24% smaller than FFV1;
- 40.54% larger than HEVC lossless.

### Foreman, medium motion

| Codec | Final bytes | % raw |
|---|---:|---:|
| HEVC lossless | **3,722,889** | **32.643%** |
| AV1 lossless | 3,790,903 | 33.240% |
| VP9 lossless | 3,809,998 | 33.407% |
| H.264 lossless | 3,893,089 | 34.136% |
| FFV1 | 5,295,415 | 46.431% |
| **AURORA full AUM** | **5,769,707** | **50.590%** |

AURORA is:
- 8.96% larger than FFV1;
- 54.98% larger than HEVC lossless.

### Bus, high motion

| Codec | Final bytes | % raw |
|---|---:|---:|
| HEVC lossless | **1,269,735** | **44.533%** |
| VP9 lossless | 1,272,775 | 44.640% |
| H.264 lossless | 1,311,224 | 45.988% |
| AV1 lossless | 1,336,862 | 46.888% |
| FFV1 | 1,593,314 | 55.882% |
| **AURORA full AUM** | **1,841,546** | **64.588%** |

AURORA is:
- 15.58% larger than FFV1;
- 45.03% larger than HEVC lossless.

## Video aggregate

Final file totals across Akiyo + Foreman + Bus:

- AURORA full AUM: **9,787,973 bytes**
- FFV1/MKV: **10,357,351 bytes**
- H.264 lossless/MKV: **6,755,013 bytes**
- HEVC lossless/MKV: **6,541,429 bytes**
- VP9 lossless/MKV: **6,780,620 bytes**
- AV1 lossless/MKV: **6,792,510 bytes**

On this controlled three-clip research corpus:

- AURORA full-stack is **5.50% smaller than FFV1**;
- AURORA is **49.63% larger than HEVC lossless**;
- AURORA is **44.90% larger than H.264 lossless**;
- AURORA is **44.35% larger than VP9 lossless**;
- AURORA is **44.11% larger than AV1 lossless**.

This is not a general codec ranking. The corpus is intentionally small and diagnostic.

## Container overhead finding

Previous best AURORA video aggregate before final AUM packaging:
- 9,784,828 bytes

Full AUM aggregate:
- 9,787,973 bytes

Difference:
- **3,145 bytes**
- approximately **0.032%**

Therefore AUM v0.1 container/index/CRC overhead is negligible on this video test.

## Speed note

Current AURORA benchmark timing is not production-representative because it still includes:
- Python frontend code;
- temporary files;
- subprocess invocation of KHEPRI EXP-37A;
- duplicate candidate work for video routing.

The mature external codecs are native optimized implementations.

Do not interpret current timing as the final expected AURORA speed.

## Engineering conclusions

1. AUM container structure is not the compression bottleneck.
2. Video low-motion compression remains a strong area for AURORA.
3. Medium/high-motion residual modeling remains the largest video weakness.
4. Short independent audio recovery packets cause a measurable compression-state reset penalty.
5. A 2-second audio recovery horizon nearly restores the earlier single-stream compression ratio.
6. Recovery horizon / KHEPRI state horizon should become an adaptive codec variable.
7. The next compression work should focus on:
   - adaptive state horizon for audio;
   - stronger motion/residual representation for video;
   - removal of Python/subprocess overhead for speed.
