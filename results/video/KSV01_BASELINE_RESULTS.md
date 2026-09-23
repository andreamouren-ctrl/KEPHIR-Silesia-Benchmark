# KS-V01 — Real Lossless Video Baseline

Date: 2026-09-23  
GitHub Actions run: 35818304677  
Result: **PASS / STRONG SIGNAL, NOT A GENERAL SUPERIORITY CLAIM**

Source: Xiph.org Derf Akiyo QCIF:
- YUV420p 8-bit
- 176 x 144
- 300 frames
- 30000/1001 fps
- 11,404,800 raw bytes
- SHA-256: `e1efee0e95c6d27aefe2294a727768334db8466e67bf4a49cf8f5b2fb8b49108`

All paths reconstructed bit-exactly.

| Codec/path | Bytes | % raw | bits/pixel | Encode realtime |
|---|---:|---:|---:|---:|
| Direct EXP-33H | 3,151,048 | 27.629% | 3.315 | 23.73x |
| LEFT + EXP-33H | 3,431,600 | 30.089% | 3.611 | 3.50x |
| PAETH + EXP-33H | 3,504,876 | 30.732% | 3.688 | 2.16x |
| Temporal GOP10 + EXP-33H | **2,211,437** | **19.390%** | **2.327** | 7.49x |
| FFV1 level 3 GOP10 | 3,468,622 | 30.414% | 3.650 | 46.22x |

## Key result

On this low-motion sequence, the reversible temporal residual path produces a final KHEPRI archive about **36.25% smaller than FFV1** under the tested settings.

This does **not** establish general superiority over FFV1:
- Akiyo is a low-motion sequence;
- only one resolution/content class has been tested;
- FFV1 is much faster in this Python-front-end prototype;
- the KSV temporal predictor is a known/background control and is not candidate IP.

## Decision

The important finding is that EXP-33H is highly effective on temporal video residuals.

Promote the **video research direction**, not the temporal predictor itself.

Next gate: test low-, medium- and higher-motion standard sequences before introducing KHEPRI-specific proprietary residual geometry for video.
