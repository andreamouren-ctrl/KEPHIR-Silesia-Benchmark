# KS-V04 — Block-Major Residual Lattice

Date: 2026-09-23  
GitHub Actions run: 35819372374  
Result: **PASS technically / HYPOTHESIS REJECTED**

All variants reconstructed bit-exactly.

| Clip | Geometry | Raster bytes | Lattice bytes | Lattice delta |
|---|---|---:|---:|---:|
| Foreman | MC16/R4 | **5,828,903** | 5,862,820 | **+0.582%** |
| Foreman | MC8/R4 | **5,781,687** | 5,801,733 | **+0.347%** |
| Bus | MC16/R4 | **1,865,101** | 1,872,772 | **+0.411%** |
| Bus | MC8/R4 | **1,842,551** | 1,847,176 | **+0.251%** |

Reference FFV1:
- Foreman: 5,295,415 bytes
- Bus: 1,593,314 bytes

## Decision

Fixed block-major serialization is rejected for KHEPRI Stream video.

The experiment disproves the simple hypothesis that making each 16x16 luma residual occupy one contiguous 256-byte region is sufficient to exploit EXP-33H's favored distance topology.

This result also reinforces the prior-art disposition: fixed residual/block scanning remains BACKGROUND and is not candidate IP.

The next experiment must model the **actual probability/match behavior** of EXP-33H rather than assuming that a geometric offset alone is beneficial.
