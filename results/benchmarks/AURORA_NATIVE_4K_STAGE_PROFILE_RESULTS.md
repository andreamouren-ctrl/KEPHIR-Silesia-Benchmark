# AURORA Native 4K Stage Profile Results

Date: 2026-09-26
GitHub Actions run: 36225901734
Status: PASS

## Profile

Pipeline:
- YUV420p8 3840x2160
- 135 tiles
- native C++20 AURORA Media
- KHEPRI EXP-37A in-process backend
- exact motion fast path
- interior-block motion fast path
- SSE2 residual encode/decode

Payload:
- **256,727 bytes**

Single-thread/sequential stage-profile timing:

### Encode

Total:
- **465.522 ms**
- **2.14813 fps**

| Stage | Time | Share |
|---|---:|---:|
| Tile extraction | 2.97542 ms | 0.639% |
| MC8R4 motion + residual generation | 15.7182 ms | 3.376% |
| Residual choose/map | 11.6246 ms | 2.497% |
| **KHEPRI EXP-37A encode** | **435.204 ms** | **93.487%** |

### Decode

Total:
- **42.3723 ms**
- **23.6003 fps**

| Stage | Time | Share |
|---|---:|---:|
| Reference tile extraction | 1.39619 ms | 3.295% |
| **KHEPRI EXP-37A decode** | **23.9979 ms** | **56.636%** |
| Residual unmap | 9.43947 ms | 22.278% |
| MC8R4 reconstruction | 6.70973 ms | 15.835% |
| Tile paste | 0.82900 ms | 1.956% |

Combined sequential pipeline:
- **507.894 ms**
- **1.96891 fps**

## Engineering conclusion

The previous assumption that MC8R4 remained the dominant encoder bottleneck is no longer true.

At the current checkpoint:
- motion search is only about **3.38%** of encode time;
- KHEPRI accounts for about **93.49%** of encode time.

Even a large relative motion-search improvement now has very small full-pipeline leverage.
For example, a 20% reduction in the motion stage can reduce total encode time by at most roughly
0.68% before secondary effects.

The next primary optimization target is therefore the KHEPRI in-memory parser/encoder.

## Next target

EXP-37A currently performs two closely related hash-chain match searches:
- traditional `findbest`;
- predictive-aware `findpred`.

Both traverse the same chain and independently compute match lengths.

Next experiment:
**fuse traditional and predictive candidate evaluation into one chain traversal while preserving
the exact candidate scores, gates, tie behavior and final token stream.**

Promotion gate:
- byte-identical KHEPRI payloads;
- byte-identical AURORA 4K payload total;
- bit-exact decode;
- material full-pipeline encode gain.
